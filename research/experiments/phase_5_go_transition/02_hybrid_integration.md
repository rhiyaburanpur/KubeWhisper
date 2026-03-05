# Experiment 5.2: Hybrid Integration — Go Agent ↔ Python Brain (HTTP + Auth)
**Date:** 2026-03-03
**Phase:** Phase 5 (The Optimization — Golang Transition)
**Subject:** Inter-Process Communication Between the Go Watcher and the Python API Server

---

## 1. Motivation
With the Go watcher operational (Experiment 5.1), the missing link is the communication
channel between the Go agent and the Python Brain. The agent must be able to POST a crash
report and receive a structured diagnosis.

**Design Constraint:** The channel must be:
1. **Stateless** — each request is self-contained (no persistent connection required).
2. **Authenticated** — the `/analyze` endpoint must not be callable by arbitrary processes
   within the cluster.
3. **Configurable** — the Brain's URL must not be hardcoded; it must resolve to a
   Kubernetes Service DNS name in production.

---

## 2. Implementation

### 2a. Python API Server (`src/brain/server.py`)
Wrapped `Synapse.reason()` in a FastAPI application exposing a single POST endpoint.

**Schema:**
```json
POST /analyze
Header: X-API-Key: <token>
Body: { "pod_name": "...", "error_log": "..." }
```

**Auth mechanism:** `APIKeyHeader` middleware from `fastapi.security`. The expected key
is read from the `KUBEWHISPERER_API_KEY` environment variable at startup. A missing or
mismatched key returns `HTTP 403 Forbidden`. A missing env var raises a `RuntimeError`
at startup, preventing a silently unauthenticated deployment.

### 2b. Go HTTP Client (`src/go-agent/main.go`)
The `sendCrashReport()` function was refactored from `http.Post()` (which does not support
custom headers) to `http.NewRequest()` + `http.DefaultClient.Do()`.

Two environment variables control the HTTP call:

| Variable | Purpose | Local Default |
|---|---|---|
| `BRAIN_URL` | Full URL to the `/analyze` endpoint | `http://localhost:8000/analyze` |
| `KUBEWHISPERER_API_KEY` | Shared secret for `X-API-Key` header | *(no default — startup fails fast)* |

**Fail-fast behavior:** If `KUBEWHISPERER_API_KEY` is unset, the Go agent logs an error
and skips the HTTP call rather than sending an unauthenticated request.

---

## 3. End-to-End Verification
1. Launched `uvicorn src.brain.server:app` (Python Brain).
2. Set `BRAIN_URL` and `KUBEWHISPERER_API_KEY` in the Go agent's environment.
3. Deployed `bad-student` pod.
4. **Go agent** detected `CrashLoopBackOff`, fetched previous logs, POSTed to Python server.
5. **Python server** authenticated the request, passed logs through RAG pipeline,
   returned JSON diagnosis.
6. **Go agent** printed the structured diagnosis to stdout.

**Confirmed failure modes:**
* Missing `X-API-Key` header → `HTTP 403` logged by Go agent, no crash.
* Brain unreachable → `connection refused` logged by Go agent, no crash. Watcher continues.

---

## 4. Engineering Notes
* **In-cluster DNS:** In production, `BRAIN_URL` will be set to
  `http://kubewhisperer-brain.default.svc.cluster.local:8000/analyze`, leveraging
  Kubernetes internal service discovery — no external networking required.
* **Secret management:** Both processes share `KUBEWHISPERER_API_KEY`. In production
  this will be provisioned as a Kubernetes `Secret` and mounted as an env var in both
  the DaemonSet (Go) and the Deployment (Python) manifests.
* **No mutual TLS required** at this stage: cluster-internal traffic is protected by
  Kubernetes Network Policies. mTLS is deferred to Phase 6.