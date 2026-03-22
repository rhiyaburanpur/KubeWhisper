# Experiment Log: Phase 8 — Gold Standard Dataset & MTTR Instrumentation

**Date:** March 2026
**Branch:** feat/phase-8-dataset
**Status:** Complete

---

## 8.1 Objective

Phase 8 constructs the evaluation foundation required to support the paper's
quantitative claims. It has two components:

1. **Gold Standard Dataset** — 50 reproducible Kubernetes failure scenarios across
   three categories, each with a documented expected root cause and remediation command
2. **MTTR Instrumentation** — per-stage timestamps injected at each step of the MAPE-K
   loop so Mean Time to Recovery is measured in milliseconds, not estimated

Without this phase, the >50% MTTR reduction claim is anecdotal. With it, every number in
the Results section is traceable to a specific scenario run recorded in `mttr_log.jsonl`.

---

## 8.2 Dataset Design

### Failure Taxonomy

| Category | Scenario IDs | Count |
|---|---|---|
| Resource errors | 01–17 | 17 |
| Config errors | 18–34 | 17 |
| Network / RBAC errors | 35–50 | 16 |

### Design Principles

**Reproducibility:** Every scenario is a single `kubectl apply -f` command. The failure
mode is deterministic — the pod will always crash in the same way on any Kind cluster.

**Watchdog coverage:** All 50 scenarios have `watchdog_resolves: false` in `manifest.json`.
This means a naive restart loop (Baseline B in Phase 10) will not fix the problem — the
container will crash again on every restart. This is critical: it establishes that
KUBEWHISPER adds value beyond what a basic liveness probe provides.

**Failure diversity:** The dataset includes failures that span both the container lifecycle
(OOMKilled, segfault, init container failure) and the cluster control plane (missing
ServiceAccount, RBAC denial, ImagePullBackOff variants, DNS failure). This prevents the
evaluation from being biased toward a single failure type.

**One scenario per unique signal:** No two scenarios produce the same exit code and log
combination. Each scenario exercises a distinct diagnostic path through the RAG pipeline.

### `dataset/manifest.json` Schema

Each entry contains:

```json
{
  "scenario_id": "01",
  "name": "oom-kill-heap",
  "category": "resource",
  "manifest_file": "scenario-01-oom-kill-heap.yaml",
  "expected_root_cause": "Container exceeds memory limit and is killed by the OOM killer",
  "expected_remediation": "kubectl set resources deployment <n> --limits=memory=256Mi",
  "watchdog_resolves": false
}
```

The `expected_root_cause` and `expected_remediation` fields are the ground truth labels
used in Phase 9 to calculate hallucination rate and in Phase 10 to evaluate diagnosis
accuracy.

---

## 8.3 MTTR Instrumentation

### Timestamp Definitions

| Timestamp | Stage | Captured By | Description |
|---|---|---|---|
| T1 (`t1_monitor_ms`) | Monitor | Go Agent | Moment the CrashLoopBackOff or ImagePullBackOff event is received from the Kubernetes API watch stream |
| T2 (`t2_analyze_ms`) | Analyze | Go Agent | Moment the previous container logs have been fetched and the crash report is ready to send |
| T3 (`t3_plan_ms`) | Plan | Python Brain | Moment the `/analyze` endpoint receives the request and begins RAG retrieval + Gemini prompt construction |
| T4 (`t4_execute_ms`) | Execute | Python Brain | Moment Gemini returns the completed diagnosis |

All timestamps are Unix epoch milliseconds (`time.Now().UnixNano() / 1e6` in Go,
`time.monotonic() * 1000` in Python).

### MTTR Calculation

```
MTTR = T4 - T1  (full pipeline, crash detection to diagnosis delivered)
```

Intermediate breakdowns available for analysis:

```
Detection latency  = T2 - T1  (how long to fetch logs after detecting crash)
Brain latency      = T4 - T3  (Gemini + RAG time inside the brain)
Network latency    = T3 - T2  (HTTP transit between agent and brain)
```

### `mttr_log.jsonl` Format

One JSON line per diagnosis. Example:

```json
{
  "trace_id": "d4d7b17b",
  "scenario_id": "01",
  "pod_name": "scenario-01-oom-heap",
  "t1_monitor_ms": 1742123456789.0,
  "t2_analyze_ms": 1742123456812.0,
  "t3_plan_ms": 1742123456830.0,
  "t4_execute_ms": 1742123466712.0,
  "mttr_ms": 9923.0,
  "rag_hit": true,
  "success": true
}
```

This file is gitignored (contains runtime data, not code). It is the raw data source for
`results.csv` in Phase 10.

---

## 8.4 Code Changes

### New: `src/brain/mttr.py`

Defines the `MTTRRecord` dataclass and `write_mttr_record()` function. Every successful
diagnosis appends one line to `mttr_log.jsonl`. The log path is configurable via
`MTTR_LOG_PATH` environment variable.

### Modified: `src/brain/server.py`

- `CrashReport` Pydantic model gains three optional fields: `scenario_id`, `t1_monitor_ms`,
  `t2_analyze_ms` — all optional so existing integrations remain compatible
- `T3` is recorded at the start of the `/analyze` handler before `brain.reason()` is called
- `T4` is recorded immediately after `brain.reason()` returns
- Full `MTTRRecord` is written to `mttr_log.jsonl` after every successful diagnosis
- Response JSON now includes a `timestamps` object with all four values and computed `mttr_ms`

### Modified: `src/go-agent/main.go`

- `CrashReport` struct gains `ScenarioID`, `T1MonitorMs`, `T2AnalyzeMs` fields
- `T1` is recorded at the moment the crash event is received in the watch loop
- `T2` is recorded inside `sendCrashReport()` immediately before the HTTP POST is built
- `nowMs()` helper returns `float64` Unix milliseconds from `time.Now().UnixNano()`
- `SCENARIO_ID` environment variable allows benchmark runner (Phase 10) to tag each run

---

## 8.5 Relevance to Research Paper

This phase directly populates the data that appears in the paper's Results section:

- `mttr_ms` per scenario → MTTR comparison table (KUBEWHISPER vs Baseline A vs Baseline B)
- `rag_hit` per scenario → RAG retrieval rate by failure category
- `t4_ms - t3_ms` → Brain-only latency, isolating Gemini API contribution to MTTR
- `scenario_id` → Joins `mttr_log.jsonl` to `dataset/manifest.json` for per-category analysis

The timestamp breakdown (T1→T2→T3→T4) also strengthens the paper's system design
section by showing exactly where time is spent in the MAPE-K pipeline.