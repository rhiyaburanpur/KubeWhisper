# Experiment 5.3: Production Hardening — Configuration & Resilience Refactors
**Date:** 2026-03-03
**Phase:** Phase 5 (The Optimization — Golang Transition)
**Subject:** Eliminating Hardcoded State and Improving Failure Semantics

---

## 1. Motivation
Code review of the Phase 4.5 Python codebase identified three categories of technical
debt that are acceptable in a prototype but constitute production defects:

| # | Issue | Location | Risk |
|---|---|---|---|
| 1 | Hardcoded `db_storage` path | `memory.py`, `synapse.py`, `librarian.py` | Path breaks in containerized deployments with mounted volumes |
| 2 | Hardcoded fallback assumes `CrashLoopBackOff` | `synapse.py` error handler | Misleading diagnosis for `OOMKilled`, `ImagePullBackOff`, etc. |
| 3 | Single hardcoded ingestion URL | `librarian.py` | Cannot scale knowledge base without code changes |

---

## 2. Corrective Actions

### Fix 1: `DB_PATH` Environment Variable
`memory.py` and `synapse.py` now resolve the persistence path via:
```python
db_path = os.getenv("DB_PATH", "db_storage")
```
The `"db_storage"` default preserves existing local development behavior. In production,
`DB_PATH` will point to a mounted `PersistentVolumeClaim` (e.g., `/data/db_storage`).

### Fix 2: Generic AI Failure Fallback
The hardcoded `CrashLoopBackOff` string in the `except` block of `Synapse.reason()` was
replaced with a generic, actionable checklist:
```
Fallback: Unable to generate AI diagnosis. Investigate manually:
1. kubectl logs <pod-name> --previous
2. kubectl describe pod <pod-name>
3. kubectl get events --sort-by='.lastTimestamp'
4. kubectl top pod <pod-name>
```
This is correct regardless of the actual failure type.

### Fix 3: YAML-Driven Knowledge Ingestion (`config/sources.yaml`)
`librarian.py` was refactored to load ingestion targets from a structured YAML config:
```yaml
sources:
  - url: "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/"
    type: "official_docs"
  - url: "https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/"
    type: "official_docs"
```
* New sources can be added (runbooks, internal wikis, GitHub docs) without modifying code.
* The config path is itself configurable via `LIBRARIAN_CONFIG` env var.

---

## 3. Outcome
All three issues resolved. The codebase now adheres fully to **12-Factor App** principles:
configuration is entirely environment-driven, and no environment-specific values are
present in the source code.

---

## 4. Engineering Notes
* These changes have no impact on the external API contract (`/analyze` endpoint schema
  is unchanged).
* The `os.makedirs(persistence_path, exist_ok=True)` call in `memory.py` was also
  hardened — previously it would throw if the directory already existed in some edge cases.
* The YAML config establishes the foundation for Phase 6's operator, where a
  `ConfigMap` will mount `sources.yaml` into the Librarian pod at a well-known path.