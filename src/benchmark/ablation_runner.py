"""
Phase 11 Ablation Runner
------------------------
Reruns the Phase 10 successful scenarios against the brain server with RAG
disabled (ablation_mode=True). This isolates how much of KubeWhisper's
performance comes from ChromaDB retrieval vs Gemini's base training data.

The Go agent is not used here. This runner:
  1. Reads the 33 successful scenarios from results.csv (Phase 10 output).
  2. Fetches pod logs directly via kubectl for each scenario.
  3. POSTs to /analyze with ablation_mode=True.
  4. Records MTTR and validation results to results_ablation.csv.

Run:
    python -m src.benchmark.ablation_runner
    python -m src.benchmark.ablation_runner 01 02 03
"""

import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

MANIFEST_PATH = Path("dataset/manifest.json")
SCENARIOS_DIR = Path("manifests/broken-scenarios")
PHASE10_RESULTS_PATH = Path("results.csv")
RESULTS_CSV_PATH = Path("results_ablation.csv")
BRAIN_URL = os.getenv("BRAIN_URL", "http://localhost:8000/analyze")
API_KEY = os.getenv("KUBEWHISPER_API_KEY", "")

REQUEST_TIMEOUT_S = 60
INTER_SCENARIO_PAUSE_S = 10

SPECIAL_CLEANUP = {
    "12": ("job", "scenario-12-job"),
    "27": ("cronjob", "scenario-27-cronjob"),
    "29": ("deployment", "scenario-29-bad-selector"),
    "31": ("deployment", "scenario-31-zero-replicas"),
}


@dataclass
class AblationResult:
    scenario_id: str
    name: str
    category: str
    status: str
    mttr_ms: Optional[float]
    validation_passed: Optional[bool]
    failure_reason: Optional[str]
    expected_root_cause: str
    diagnosed_root_cause: Optional[str]
    confidence: Optional[float]
    manifest_file: str


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_kubectl(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        ["kubectl"] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def load_manifest() -> list[dict]:
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def load_phase10_successful_ids() -> set[str]:
    """
    Reads results.csv from Phase 10 and returns the set of scenario_ids
    that completed with status SUCCESS. The ablation only reruns these
    scenarios because timed-out and errored scenarios never produced logs
    that the Go agent could retrieve, so there is nothing meaningful to
    compare against.
    """
    if not PHASE10_RESULTS_PATH.exists():
        log(f"ERROR: {PHASE10_RESULTS_PATH} not found.")
        log("Run the Phase 10 benchmark first: python -m src.benchmark.runner")
        sys.exit(1)

    successful = set()
    with open(PHASE10_RESULTS_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "SUCCESS":
                successful.add(row["scenario_id"])

    log(f"Loaded {len(successful)} successful scenario IDs from {PHASE10_RESULTS_PATH}")
    return successful


def apply_scenario(manifest_file: str) -> bool:
    path = SCENARIOS_DIR / manifest_file
    rc, _, err = run_kubectl(["apply", "-f", str(path)])
    if rc != 0:
        log(f"  kubectl apply failed: {err}")
        return False
    return True


def cleanup_scenario(scenario_id: str, manifest_file: str) -> None:
    if scenario_id in SPECIAL_CLEANUP:
        kind, name = SPECIAL_CLEANUP[scenario_id]
        run_kubectl(["delete", kind, name, "--ignore-not-found=true"])
    path = SCENARIOS_DIR / manifest_file
    run_kubectl(["delete", "-f", str(path), "--ignore-not-found=true"])


def get_pod_name_from_manifest(scenario_id: str, manifest_file: str) -> Optional[str]:
    if scenario_id in SPECIAL_CLEANUP:
        _, name = SPECIAL_CLEANUP[scenario_id]
        return name
    path = SCENARIOS_DIR / manifest_file
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("name:") and f"scenario-{scenario_id}-" in line:
                return line.split("name:")[-1].strip()
    return None


def fetch_pod_logs(pod_name: str, timeout_s: int = 30) -> Optional[str]:
    """
    Waits for a pod to reach CrashLoopBackOff or ImagePullBackOff, then
    fetches its logs. Returns None if the pod never enters a crash state
    within timeout_s.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rc, stdout, _ = run_kubectl(["get", "pod", pod_name, "-o", "json"])
        if rc != 0:
            time.sleep(2)
            continue

        try:
            pod_json = json.loads(stdout)
        except json.JSONDecodeError:
            time.sleep(2)
            continue

        container_statuses = (
            pod_json.get("status", {}).get("containerStatuses") or []
        )
        for cs in container_statuses:
            waiting = (cs.get("state") or {}).get("waiting") or {}
            reason = waiting.get("reason", "")
            if reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                rc_log, logs, _ = run_kubectl(
                    ["logs", pod_name, "--previous", "--tail=50"]
                )
                if rc_log == 0 and logs:
                    return logs
                rc_log, logs, _ = run_kubectl(["logs", pod_name, "--tail=50"])
                if rc_log == 0 and logs:
                    return logs
                return f"Pod {pod_name} is in {reason} but logs are empty."

        elapsed = int(timeout_s - (deadline - time.time()))
        log(f"  Waiting for crash state... ({elapsed}s elapsed)")
        time.sleep(3)

    return None


def call_brain_ablation(
    pod_name: str,
    error_log: str,
    scenario_id: str,
    t1_ms: float,
) -> Optional[dict]:
    """
    POSTs to /analyze with ablation_mode=True. Returns the parsed JSON
    response, or None if the request fails.
    """
    payload = {
        "pod_name": pod_name,
        "error_log": error_log,
        "scenario_id": scenario_id,
        "t1_monitor_ms": t1_ms,
        "ablation_mode": True,
    }
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            BRAIN_URL,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        log(f"  Brain returned HTTP {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        log(f"  Brain request failed: {e}")
        return None


def extract_root_cause(diagnosis_str: str) -> Optional[str]:
    """
    Attempts to parse the root_cause field from the diagnosis JSON string.
    Returns None if parsing fails — treated as a hallucination in the summary.
    """
    import re
    match = re.search(r"```json\s*(.*?)\s*```", diagnosis_str, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\})", diagnosis_str, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data.get("root_cause")
    except Exception:
        return None


def extract_confidence(diagnosis_str: str) -> Optional[float]:
    import re
    match = re.search(r"```json\s*(.*?)\s*```", diagnosis_str, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\})", diagnosis_str, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data.get("confidence")
    except Exception:
        return None


def write_results_csv(results: list[AblationResult]) -> None:
    fieldnames = [f.name for f in fields(AblationResult)]
    with open(RESULTS_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    log(f"Results written to {RESULTS_CSV_PATH}")


def print_summary(results: list[AblationResult]) -> None:
    total = len(results)
    success = sum(1 for r in results if r.status == "SUCCESS")
    timeout = sum(1 for r in results if r.status == "TIMEOUT")
    error = sum(1 for r in results if r.status == "ERROR")

    mttr_values = [r.mttr_ms for r in results if r.mttr_ms is not None]
    avg_mttr = sum(mttr_values) / len(mttr_values) if mttr_values else 0

    validation_results = [r.validation_passed for r in results if r.validation_passed is not None]
    pass_count = sum(1 for v in validation_results if v)
    hallucination_rate = (
        1 - (pass_count / len(validation_results)) if validation_results else 0
    )

    print("\n" + "=" * 60)
    print("KUBEWHISPER ABLATION STUDY SUMMARY (RAG DISABLED)")
    print("=" * 60)
    print(f"Total scenarios:      {total}")
    print(f"Successful:           {success}")
    print(f"Timed out:            {timeout}")
    print(f"Errors:               {error}")
    print(f"Average MTTR:         {avg_mttr:.1f} ms ({avg_mttr/1000:.2f}s)")
    print(f"Hallucination rate:   {hallucination_rate:.1%}")
    print("=" * 60)

    if timeout > 0:
        print("Timed out scenarios:")
        for r in results:
            if r.status == "TIMEOUT":
                print(f"  - {r.scenario_id}: {r.name}")
    print()


def validate_env() -> bool:
    missing = []
    if not os.getenv("KUBEWHISPER_API_KEY"):
        missing.append("KUBEWHISPER_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        log(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        return False
    return True


def run_ablation(scenario_ids: Optional[list[str]] = None) -> None:
    if not validate_env():
        sys.exit(1)

    successful_ids = load_phase10_successful_ids()
    all_scenarios = load_manifest()

    scenarios = [
        s for s in all_scenarios
        if s["scenario_id"] in successful_ids
    ]

    if scenario_ids:
        scenarios = [s for s in scenarios if s["scenario_id"] in scenario_ids]

    log(f"Ablation run: {len(scenarios)} scenarios (RAG disabled)")
    log(f"Brain URL: {BRAIN_URL}")
    log(f"Results will be written to: {RESULTS_CSV_PATH}")
    log("Make sure the brain is running: uvicorn src.brain.server:app --host 0.0.0.0 --port 8000")
    print()

    results: list[AblationResult] = []

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["scenario_id"]
        name = scenario["name"]
        category = scenario["category"]
        manifest_file = scenario["manifest_file"]

        log(f"[{i}/{len(scenarios)}] Scenario {sid}: {name} ({category})")

        applied = apply_scenario(manifest_file)
        if not applied:
            results.append(AblationResult(
                scenario_id=sid, name=name, category=category,
                status="ERROR", mttr_ms=None, validation_passed=None,
                failure_reason="kubectl apply failed",
                expected_root_cause=scenario["expected_root_cause"],
                diagnosed_root_cause=None, confidence=None,
                manifest_file=manifest_file,
            ))
            log(f"  ERROR: could not apply manifest. Skipping.")
            time.sleep(INTER_SCENARIO_PAUSE_S)
            continue

        t1_ms = time.time() * 1000

        pod_name = get_pod_name_from_manifest(sid, manifest_file)
        if not pod_name:
            cleanup_scenario(sid, manifest_file)
            results.append(AblationResult(
                scenario_id=sid, name=name, category=category,
                status="ERROR", mttr_ms=None, validation_passed=None,
                failure_reason="could not determine pod name from manifest",
                expected_root_cause=scenario["expected_root_cause"],
                diagnosed_root_cause=None, confidence=None,
                manifest_file=manifest_file,
            ))
            log(f"  ERROR: could not determine pod name.")
            time.sleep(INTER_SCENARIO_PAUSE_S)
            continue

        log(f"  Waiting for pod {pod_name} to crash...")
        error_log = fetch_pod_logs(pod_name, timeout_s=60)

        if error_log is None:
            cleanup_scenario(sid, manifest_file)
            results.append(AblationResult(
                scenario_id=sid, name=name, category=category,
                status="TIMEOUT", mttr_ms=None, validation_passed=None,
                failure_reason="pod did not enter crash state within 60s",
                expected_root_cause=scenario["expected_root_cause"],
                diagnosed_root_cause=None, confidence=None,
                manifest_file=manifest_file,
            ))
            log(f"  TIMEOUT: pod never entered crash state.")
            time.sleep(INTER_SCENARIO_PAUSE_S)
            continue

        log(f"  Logs fetched ({len(error_log)} chars). Calling brain (ablation_mode=True)...")
        response = call_brain_ablation(pod_name, error_log, sid, t1_ms)

        cleanup_scenario(sid, manifest_file)

        if response is None:
            results.append(AblationResult(
                scenario_id=sid, name=name, category=category,
                status="ERROR", mttr_ms=None, validation_passed=None,
                failure_reason="brain request failed",
                expected_root_cause=scenario["expected_root_cause"],
                diagnosed_root_cause=None, confidence=None,
                manifest_file=manifest_file,
            ))
            log(f"  ERROR: brain did not respond.")
        else:
            timestamps = response.get("timestamps", {})
            mttr_ms = timestamps.get("mttr_ms")
            validation_passed = response.get("validation_passed", False)
            failure_reason = response.get("failure_reason")
            diagnosis_str = response.get("diagnosis", "")
            diagnosed_root_cause = extract_root_cause(diagnosis_str)
            confidence = extract_confidence(diagnosis_str)

            log(
                f"  SUCCESS: MTTR={mttr_ms:.0f}ms, "
                f"validation={validation_passed}, "
                f"root_cause={diagnosed_root_cause}"
            )
            results.append(AblationResult(
                scenario_id=sid, name=name, category=category,
                status="SUCCESS", mttr_ms=mttr_ms,
                validation_passed=validation_passed,
                failure_reason=failure_reason,
                expected_root_cause=scenario["expected_root_cause"],
                diagnosed_root_cause=diagnosed_root_cause,
                confidence=confidence,
                manifest_file=manifest_file,
            ))

        write_results_csv(results)
        log(f"  Pausing {INTER_SCENARIO_PAUSE_S}s before next scenario...")
        print()
        time.sleep(INTER_SCENARIO_PAUSE_S)

    print_summary(results)
    write_results_csv(results)


if __name__ == "__main__":
    specific = sys.argv[1:] if len(sys.argv) > 1 else None
    run_ablation(scenario_ids=specific)