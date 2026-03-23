import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

MANIFEST_PATH = Path("dataset/manifest.json")
SCENARIOS_DIR = Path("manifests/broken-scenarios")
MTTR_LOG_PATH = Path(os.getenv("MTTR_LOG_PATH", "mttr_log.jsonl"))
RESULTS_CSV_PATH = Path("results.csv")
GO_AGENT_DIR = Path("src/go-agent")

SCENARIO_TIMEOUT_S = 90
INTER_SCENARIO_PAUSE_S = 10
AGENT_STARTUP_WAIT_S = 3

SPECIAL_CLEANUP = {
    "12": ("job", "scenario-12-job"),
    "27": ("cronjob", "scenario-27-cronjob"),
    "29": ("deployment", "scenario-29-bad-selector"),
    "31": ("deployment", "scenario-31-zero-replicas"),
}


@dataclass
class BenchmarkResult:
    scenario_id: str
    name: str
    category: str
    status: str
    mttr_ms: Optional[float]
    rag_hit: Optional[bool]
    validation_passed: Optional[bool]
    t1_monitor_ms: Optional[float]
    t2_analyze_ms: Optional[float]
    t3_plan_ms: Optional[float]
    t4_execute_ms: Optional[float]
    expected_root_cause: str
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


def apply_scenario(manifest_file: str) -> bool:
    path = SCENARIOS_DIR / manifest_file
    rc, _, err = run_kubectl(["apply", "-f", str(path)])
    if rc != 0:
        log(f"  kubectl apply failed: {err}")
        return False
    return True


def cleanup_scenario(scenario_id: str, pod_name: str) -> None:
    if scenario_id in SPECIAL_CLEANUP:
        kind, name = SPECIAL_CLEANUP[scenario_id]
        run_kubectl(["delete", kind, name, "--ignore-not-found=true"])
    else:
        run_kubectl(["delete", "pod", pod_name, "--ignore-not-found=true"])

    manifest_file = next(
        (s["manifest_file"] for s in load_manifest() if s["scenario_id"] == scenario_id),
        None
    )
    if manifest_file:
        path = SCENARIOS_DIR / manifest_file
        run_kubectl(["delete", "-f", str(path), "--ignore-not-found=true"])


def load_manifest() -> list[dict]:
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def get_pod_name(scenario_id: str, manifest_file: str) -> str:
    if scenario_id in SPECIAL_CLEANUP:
        kind, parent_name = SPECIAL_CLEANUP[scenario_id]
        return f"{parent_name}-*"
    path = SCENARIOS_DIR / manifest_file
    with open(path) as f:
        content = f.read()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("name:") and f"scenario-{scenario_id}-" in line:
            return line.split("name:")[-1].strip()
    return f"scenario-{scenario_id}-unknown"


def wait_for_mttr_record(scenario_id: str, existing_count: int) -> Optional[dict]:
    deadline = time.time() + SCENARIO_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(2)
        if not MTTR_LOG_PATH.exists():
            continue
        with open(MTTR_LOG_PATH) as f:
            lines = f.readlines()
        if len(lines) <= existing_count:
            continue
        for line in lines[existing_count:]:
            try:
                record = json.loads(line.strip())
                if record.get("scenario_id") == scenario_id:
                    return record
            except json.JSONDecodeError:
                continue
        elapsed = int(SCENARIO_TIMEOUT_S - (deadline - time.time()))
        log(f"  Waiting for diagnosis... ({elapsed}s elapsed)")
    return None


def count_mttr_records() -> int:
    if not MTTR_LOG_PATH.exists():
        return 0
    with open(MTTR_LOG_PATH) as f:
        return sum(1 for line in f if line.strip())

import platform
AGENT_BINARY = GO_AGENT_DIR / ("kubewhisper-agent.exe" if platform.system() == "Windows" else "kubewhisper-agent")

def build_go_agent() -> None:
    log("Building Go agent binary...")
    binary_name = "kubewhisper-agent.exe" if platform.system() == "Windows" else "kubewhisper-agent"
    result = subprocess.run(
        ["go", "build", "-o", binary_name, "."],
        cwd=str(GO_AGENT_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"ERROR: Go build failed:\n{result.stderr}")
        sys.exit(1)
    log("Go agent built successfully.")


def start_go_agent(scenario_id: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["SCENARIO_ID"] = scenario_id
    env["BRAIN_URL"] = os.getenv("BRAIN_URL", "http://localhost:8000/analyze")
    env["KUBEWHISPER_API_KEY"] = os.getenv("KUBEWHISPER_API_KEY", "")

    proc = subprocess.Popen(
        [str(AGENT_BINARY)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(AGENT_STARTUP_WAIT_S)
    return proc

def stop_go_agent(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def write_results_csv(results: list[BenchmarkResult]) -> None:
    fieldnames = [f.name for f in fields(BenchmarkResult)]
    with open(RESULTS_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    log(f"Results written to {RESULTS_CSV_PATH}")


def print_summary(results: list[BenchmarkResult]) -> None:
    total = len(results)
    success = sum(1 for r in results if r.status == "SUCCESS")
    timeout = sum(1 for r in results if r.status == "TIMEOUT")
    error = sum(1 for r in results if r.status == "ERROR")

    mttr_values = [r.mttr_ms for r in results if r.mttr_ms is not None]
    avg_mttr = sum(mttr_values) / len(mttr_values) if mttr_values else 0

    validation_results = [r.validation_passed for r in results if r.validation_passed is not None]
    pass_count = sum(1 for v in validation_results if v)
    hallucination_rate = 1 - (pass_count / len(validation_results)) if validation_results else 0

    rag_hits = [r.rag_hit for r in results if r.rag_hit is not None]
    rag_hit_rate = sum(1 for h in rag_hits if h) / len(rag_hits) if rag_hits else 0

    print("\n" + "=" * 60)
    print("KUBEWHISPER BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total scenarios:      {total}")
    print(f"Successful:           {success}")
    print(f"Timed out:            {timeout}")
    print(f"Errors:               {error}")
    print(f"Average MTTR:         {avg_mttr:.1f} ms ({avg_mttr/1000:.2f}s)")
    print(f"RAG hit rate:         {rag_hit_rate:.1%}")
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
        missing.append("KUBEWHISPERER_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        log(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        log("Make sure your .env file is populated and the brain is running.")
        return False
    return True


def run_benchmark(scenario_ids: Optional[list[str]] = None) -> None:
    if not validate_env():
        sys.exit(1)
    
    build_go_agent()

    scenarios = load_manifest()
    if scenario_ids:
        scenarios = [s for s in scenarios if s["scenario_id"] in scenario_ids]

    log(f"Starting benchmark: {len(scenarios)} scenarios")
    log(f"Timeout per scenario: {SCENARIO_TIMEOUT_S}s")
    log(f"Results will be written to: {RESULTS_CSV_PATH}")
    log("Make sure the brain is running: uvicorn src.brain.server:app --host 0.0.0.0 --port 8000")
    print()

    results: list[BenchmarkResult] = []

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["scenario_id"]
        name = scenario["name"]
        category = scenario["category"]
        manifest_file = scenario["manifest_file"]

        log(f"[{i}/{len(scenarios)}] Scenario {sid}: {name} ({category})")

        pod_name = get_pod_name(sid, manifest_file)
        existing_count = count_mttr_records()

        agent_proc = start_go_agent(sid)
        log(f"  Go agent started (PID {agent_proc.pid}, SCENARIO_ID={sid})")

        applied = apply_scenario(manifest_file)
        if not applied:
            stop_go_agent(agent_proc)
            results.append(BenchmarkResult(
                scenario_id=sid, name=name, category=category,
                status="ERROR", mttr_ms=None, rag_hit=None,
                validation_passed=None,
                t1_monitor_ms=None, t2_analyze_ms=None,
                t3_plan_ms=None, t4_execute_ms=None,
                expected_root_cause=scenario["expected_root_cause"],
                manifest_file=manifest_file,
            ))
            log(f"  ERROR: could not apply manifest. Skipping.")
            time.sleep(INTER_SCENARIO_PAUSE_S)
            continue

        log(f"  Manifest applied. Waiting for crash detection...")

        mttr_record = wait_for_mttr_record(sid, existing_count)

        stop_go_agent(agent_proc)
        cleanup_scenario(sid, pod_name)

        if mttr_record is None:
            log(f"  TIMEOUT after {SCENARIO_TIMEOUT_S}s")
            results.append(BenchmarkResult(
                scenario_id=sid, name=name, category=category,
                status="TIMEOUT", mttr_ms=None, rag_hit=None,
                validation_passed=None,
                t1_monitor_ms=None, t2_analyze_ms=None,
                t3_plan_ms=None, t4_execute_ms=None,
                expected_root_cause=scenario["expected_root_cause"],
                manifest_file=manifest_file,
            ))
        else:
            mttr_ms = mttr_record.get("mttr_ms")
            log(f"  SUCCESS: MTTR = {mttr_ms:.0f} ms ({mttr_ms/1000:.2f}s), rag_hit={mttr_record.get('rag_hit')}")
            results.append(BenchmarkResult(
                scenario_id=sid, name=name, category=category,
                status="SUCCESS", mttr_ms=mttr_ms,
                rag_hit=mttr_record.get("rag_hit"),
                validation_passed=mttr_record.get("success"),
                t1_monitor_ms=mttr_record.get("t1_monitor_ms"),
                t2_analyze_ms=mttr_record.get("t2_analyze_ms"),
                t3_plan_ms=mttr_record.get("t3_plan_ms"),
                t4_execute_ms=mttr_record.get("t4_execute_ms"),
                expected_root_cause=scenario["expected_root_cause"],
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
    run_benchmark(scenario_ids=specific)