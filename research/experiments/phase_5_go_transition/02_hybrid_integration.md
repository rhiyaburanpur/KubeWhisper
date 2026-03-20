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

**Date verified:** 2026-03-05

**Terminal 1 (Python Brain) output:**
```
[server] Received crash report for: bad-student
[synapse] Retrieving relevant knowledge...
[synapse] Retrieved context: OOMKilled means Out Of Memory. It happens when
a container uses more RAM than allowed....
[synapse] Consulting Gemini AI...
[synapse] Analysis complete.
```

**Terminal 2 (Go Agent) output:**
```
[!] CRASH DETECTED: Pod bad-student -> CrashLoopBackOff
[->] Sending crash report for bad-student to Neural Engine...
{"pod":"bad-student","diagnosis":"**Root Cause:** The container running the
application attempted to allocate more memory than its configured
limits.memory resource, leading to an Out-Of-Memory error within the
application itself.\n\n**Fix Command:**\n```bash\nkubectl set resources
deployment/<your-deployment-name> -c <your-container-name>
--limits=memory=1Gi\n```"}
```

**Result:** PASS. Full RAG cycle completed. ChromaDB retrieved the correct
OOMKilled context chunk from Phase 2 ingestion. Gemini returned a structured
root cause and actionable kubectl fix command.
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