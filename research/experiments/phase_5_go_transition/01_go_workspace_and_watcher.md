# Experiment 5.1: Go Agent — Workspace Initialization & Kubernetes Watcher
**Date:** 2026-03-03
**Phase:** Phase 5 (The Optimization — Golang Transition)
**Subject:** Replacing the Python Observer with a Compiled Go Binary

---

## 1. Motivation
The Python monolith (Phase 4) co-located the cluster observer and the AI reasoning engine
in a single process. While effective, this architecture has a critical production constraint:
a Python process with loaded ML dependencies (`sentence-transformers`, `chromadb`) consumes
**100MB+ of resident memory**. In a production Kubernetes cluster where the agent must run
as a DaemonSet (one instance per node), this overhead is unacceptable at scale.

**Architectural Decision:** Decouple the system along its natural boundary:
* **Observer (Go):** Stateless, compiled binary. Target footprint: <20MB.
* **Brain (Python):** Stateful AI service, runs as a central Deployment. Called over HTTP.

---

## 2. Implementation

**Step 1: Go Module Initialization**
```bash
cd src/go-agent
go mod init kubewhisperer-agent
go get k8s.io/client-go@latest
go get k8s.io/apimachinery@latest
```

**Step 2: Kubeconfig Loading**
The agent uses `clientcmd.BuildConfigFromFlags` to load the kubeconfig from
`$HOME/.kube/config`, mirroring the Python agent's `config.load_kube_config()` behavior.
This keeps the local development workflow identical.

**Step 3: Event Watcher**
Implemented `clientset.CoreV1().Pods("default").Watch(...)` with a filter on
`event.Type == "MODIFIED"` and `containerStatus.State.Waiting.Reason`.

Crash states detected:
* `CrashLoopBackOff`
* `ImagePullBackOff`

**Step 4: Deduplication Cache (Port from Python)**
The Python agent's `diagnosis_cache` (TTL = 5 minutes) was re-implemented in Go
using a `map[string]time.Time` and a `cacheTTL` constant. Behavior is identical.

---

## 3. Verification
* Deployed `bad-student` pod to local Kind cluster.
* Go binary successfully detected the `CrashLoopBackOff` state transition and printed the
  pod name and reason to stdout.
* Cache correctly suppressed repeat events within the 5-minute TTL window.

---

## 4. Engineering Notes
* **Language boundary is clean:** The Go agent has zero knowledge of ML, embeddings, or
  the Gemini API. It is a pure event router.
* **Binary size:** Compiled Go binary is ~8MB, a ~92% reduction versus the Python process.
* **Cross-compilation:** The Go binary can be cross-compiled for `linux/amd64` and
  `linux/arm64` from a Windows/macOS dev machine with a single `GOOS=linux go build` command,
  which simplifies the container image build pipeline.