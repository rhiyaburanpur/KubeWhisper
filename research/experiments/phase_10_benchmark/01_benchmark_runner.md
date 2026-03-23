# Phase 10 — Automated Benchmark Runner

## Objective

Run all 50 failure scenarios automatically and produce `results.csv` — the core
data table for the research paper. Measures MTTR, RAG hit rate, and hallucination
rate across the full dataset.

## New Files

- `src/benchmark/runner.py` — fully automated benchmark runner
- `src/benchmark/__init__.py` — module marker
- `results.csv` — output (gitignored, generated at runtime)

## How to Run

Prerequisites: brain must be running in a separate terminal.

```powershell
# Terminal 1: start the brain
uvicorn src.brain.server:app --host 0.0.0.0 --port 8000

# Terminal 2: run the full benchmark
python -m src.benchmark.runner
```

Run a single scenario for testing:
```powershell
python -m src.benchmark.runner 01
```

Run a subset:
```powershell
python -m src.benchmark.runner 01 02 03
```

## results.csv Columns

| Column | Description |
|---|---|
| scenario_id | 01–50 |
| name | scenario short name |
| category | resource / config / network |
| status | SUCCESS / TIMEOUT / ERROR |
| mttr_ms | end-to-end MTTR in milliseconds |
| rag_hit | true if ChromaDB returned context |
| validation_passed | true if schema + allowlist passed |
| t1_monitor_ms through t4_execute_ms | per-stage timestamps |
| expected_root_cause | ground truth label from manifest.json |
| manifest_file | YAML filename |

## Design Decisions

- Go agent is started/stopped as a subprocess per scenario with SCENARIO_ID injected
  into its environment. This ensures mttr_log.jsonl records are labelled correctly.
- Runner polls mttr_log.jsonl for a new record matching the current scenario_id
  rather than parsing Go agent stdout, making it robust to log format changes.
- Timeout per scenario: 90 seconds. On timeout, status is TIMEOUT in results.csv
  and the benchmark continues to the next scenario.
- Inter-scenario pause: 10 seconds. Allows Kubernetes to fully terminate pods and
  clear the Go agent's deduplication cache between runs.
- Special cleanup for scenarios 12 (Job), 27 (CronJob), 29, 31 (Deployments):
  parent resource is deleted in addition to any pods.
- results.csv is written after every scenario, not just at the end. If the benchmark
  crashes mid-run, partial results are preserved.

## Status

Implementation complete. Full benchmark run pending.