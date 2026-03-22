# KUBEWHISPER

> An autonomic Kubernetes failure-analysis agent built on the MAPE-K control loop.
> Watches your cluster in real time, intercepts pod failures, and delivers
> RAG-augmented root-cause diagnoses with per-stage MTTR instrumentation.

**Instrumented result (Scenario 01):** 6.8 seconds end-to-end MTTR vs 60+ seconds manual — 88% reduction.
Full evaluation across 50 scenarios in progress.

---

## Research Context

This repository is the implementation artifact for an active research paper:

> **A Comparative Analysis of RAG vs. Fine-tuned LLMs for Autonomous Kubernetes Failure Recovery**
> R. Buranpur — Targeting SREcon → ACM SoCC → USENIX ATC

**Hypothesis:** A RAG-augmented agent implementing the MAPE-K model (Monitor, Analyze, Plan,
Execute, Knowledge) can reduce MTTR by >50% while maintaining a <2% hallucination rate in
autonomous Kubernetes patching logic.

Experiment logs are in `research/experiments/`. Paper drafts are in `research/paper_drafts/`.

---

## What Problem Does This Solve?

When a pod crashes in Kubernetes, the platform restarts it automatically. What it does not
do is explain *why* it crashed.

An on-call engineer must manually run `kubectl get pods`, notice the `CrashLoopBackOff`,
fetch the logs, read them, cross-reference documentation, and decide on a fix. In our
baseline study this process takes **over 60 seconds** even for experienced operators —
and longer for transient crashes where logs disappear between restarts.

KUBEWHISPER eliminates that gap. From the moment a pod enters `CrashLoopBackOff`, the
system captures logs, retrieves relevant documentation from a local vector database, and
returns a structured root-cause + `kubectl` fix command with full MAPE-K stage timestamps.

---

## Architecture

KUBEWHISPER is a hybrid system split across two processes that communicate over HTTP.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Kubernetes Cluster                           │
│                                                                      │
│   [Crashing Pod]  ──event──►  [Go Agent]         ~8MB binary        │
│                                    │                                 │
│                              T1: Crash detected                      │
│                              T2: Logs fetched                        │
│                                    │                                 │
│                          HTTP POST /analyze                          │
│                          X-API-Key + T1 + T2                        │
│                                    │                                 │
│                                    ▼                                 │
│                          [Python Brain — FastAPI]                    │
│                                    │                                 │
│                     T3: RAG retrieval begins                         │
│                                    │                                 │
│                     ┌──────────────┴──────────────┐                 │
│                     ▼                             ▼                 │
│              [ChromaDB]                  [Gemini 2.5 Flash]         │
│              Semantic search             LLM reasoning               │
│              all-MiniLM-L6-v2            RAG-augmented prompt        │
│                     └──────────────┬──────────────┘                 │
│                                    │                                 │
│                     T4: Diagnosis returned                           │
│                                    │                                 │
│              MTTR = T4 - T1  written to mttr_log.jsonl              │
│                                    ▼                                 │
│                     Root Cause + kubectl fix + timestamps            │
└──────────────────────────────────────────────────────────────────────┘
```

### MAPE-K Mapping

| Stage | Component | Description |
|---|---|---|
| Monitor | Go Agent | Watches Kubernetes event stream via `client-go` |
| Analyze | Go Agent | Fetches last 50 log lines from crashed container |
| Plan | Python Brain | RAG retrieval + Gemini prompt construction |
| Execute | Python Brain | Gemini generates root cause + remediation command |
| Knowledge | ChromaDB | Vector store of embedded Kubernetes documentation |

---

## Project Structure

```
kubewhisper/
├── src/
│   ├── go-agent/
│   │   ├── main.go              Go watcher, circuit breaker, MTTR timestamps
│   │   ├── go.mod
│   │   └── go.sum
│   ├── brain/
│   │   ├── server.py            FastAPI server, /analyze, /metrics endpoints
│   │   ├── synapse.py           RAG pipeline + Gemini reasoning
│   │   ├── memory.py            ChromaDB vector store
│   │   ├── librarian.py         ETL: scrape → chunk → embed
│   │   ├── metrics.py           Prometheus metric definitions
│   │   ├── mttr.py              MTTR recorder, writes mttr_log.jsonl
│   │   └── test_gemini_connection.py
│   ├── agent/
│   │   └── main.py              Python watcher (Phase 4, superseded by Go agent)
│   └── cli/                     Reserved for Phase 6 CLI
├── dataset/
│   └── manifest.json            50-scenario Gold Standard dataset metadata
├── manifests/
│   └── broken-scenarios/        50 reproducible failure scenario YAMLs
│       ├── scenario-01-oom-kill-heap.yaml
│       ├── scenario-02-exit-code-1-generic.yaml
│       └── ... (50 total across resource, config, network categories)
├── k8s/
│   ├── brain-deployment.yaml    Kubernetes Deployment + Service for Python Brain
│   ├── agent-daemonset.yaml     DaemonSet + RBAC for Go Agent
│   ├── configmap.yaml           Mounts sources.yaml into Brain pod
│   └── secret.yaml              Secret template for API keys
├── config/
│   └── sources.yaml             Librarian ingestion source list
├── research/
│   ├── experiments/
│   │   ├── phase_1_observer/
│   │   ├── phase_2_knowledge/
│   │   ├── phase_3_reasoner/
│   │   ├── phase_4_agent/
│   │   ├── phase_5_go_transition/
│   │   ├── phase_7_observability/
│   │   └── phase_8_dataset/
│   └── paper_drafts/
│       ├── 00_abstract.md
│       ├── 01_Introduction.md
│       ├── 02_methodology.md
│       └── 03_implementation.md
├── Dockerfile.brain             Multi-stage Python Brain image
├── Dockerfile.agent             Multi-stage Go Agent image (distroless, ~10MB)
├── .env.example                 Environment variable template
├── requirements.txt
└── README.md
```

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Brain server + RAG pipeline |
| Go | 1.21+ | Watcher agent |
| Docker | any | Required by Kind |
| Kind | any | Local Kubernetes cluster |
| kubectl | any | Cluster interaction |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/rhiyaburanpur/KubeWhisper.git
cd KubeWhisper
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
GEMINI_API_KEY=your_google_gemini_api_key_here
KUBEWHISPER_API_KEY=any_strong_random_string_you_choose
DB_PATH=db_storage
```

`GEMINI_API_KEY` — get this from [Google AI Studio](https://aistudio.google.com/app/apikey).

`KUBEWHISPER_API_KEY` — shared secret between the Go agent and the Python Brain.
Generate one with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the local Kubernetes cluster

```bash
kind create cluster --name kubewhisper-lab
kubectl cluster-info --context kind-kubewhisper-lab
```

### 5. Populate the knowledge base

Scrapes official Kubernetes documentation and loads it into ChromaDB.
Run once before the first use, and again whenever you add sources to `config/sources.yaml`.

```bash
python -m src.brain.librarian
```

---

## Running the System

You need two terminals running simultaneously.

### Terminal 1 — Python Brain

```bash
uvicorn src.brain.server:app --host 0.0.0.0 --port 8000
```

Expected startup output:
```
{"level": "info", "service": "brain", "msg": "Loading Synapse model..."}
{"level": "info", "service": "brain", "msg": "Brain online."}
INFO: Uvicorn running on http://0.0.0.0:8000
```

Verify:
```bash
curl http://localhost:8000/
# {"status":"neural_link_active"}

curl http://localhost:8000/metrics
# Prometheus metrics output
```

### Terminal 2 — Go Agent

**Linux / macOS:**
```bash
cd src/go-agent
export BRAIN_URL=http://localhost:8000/analyze
export KUBEWHISPER_API_KEY=your_key_from_env
go run .
```

**Windows (PowerShell):**
```powershell
cd src\go-agent
$env:BRAIN_URL = "http://localhost:8000/analyze"
$env:KUBEWHISPER_API_KEY = "your_key_from_env"
go run .
```

Expected startup output:
```json
{"level":"info","service":"go-agent","msg":"KUBEWHISPER Go-Agent starting"}
{"level":"info","service":"go-agent","msg":"Watching for CrashLoopBackOff and ImagePullBackOff events"}
```

### Trigger a test scenario

```bash
kubectl apply -f manifests/broken-scenarios/scenario-01-oom-kill-heap.yaml
```

Expected agent output:
```json
{"level":"warn","service":"go-agent","msg":"Crash detected: CrashLoopBackOff","pod":"scenario-01-oom-heap"}
{"level":"info","service":"go-agent","msg":"Sending crash report to brain","pod":"scenario-01-oom-heap","trace_id":"7ef6448f"}
{"level":"info","service":"go-agent","msg":"Diagnosis received","pod":"scenario-01-oom-heap","trace_id":"7ef6448f"}
```

Expected brain output:
```json
{"level":"info","service":"brain","msg":"Crash report received","trace_id":"7ef6448f","pod":"scenario-01-oom-heap"}
{"level":"info","service":"brain","msg":"Diagnosis complete","trace_id":"7ef6448f","pod":"scenario-01-oom-heap","duration_seconds":6.823,"rag_hit":true}
```

The `trace_id` is identical across both processes — a single incident can be traced
end-to-end across the agent and brain logs.

MTTR data is appended to `mttr_log.jsonl`:
```json
{"trace_id":"7ef6448f","scenario_id":"unknown","pod_name":"scenario-01-oom-heap",
 "t1_monitor_ms":1774168532260.8,"t2_analyze_ms":1774168532283.2,
 "t3_plan_ms":1774168532301.2,"t4_execute_ms":1774168539084.1,
 "mttr_ms":6823.3,"rag_hit":true,"success":true}
```

Clean up after testing:
```bash
kubectl delete pod scenario-01-oom-heap
```

---

## API Reference

### `POST /analyze`

Receives a crash report from the Go Agent and returns a structured diagnosis.

**Request:**
```
POST /analyze
X-API-Key: <KUBEWHISPER_API_KEY>
Content-Type: application/json

{
  "pod_name": "scenario-01-oom-heap",
  "error_log": "...",
  "scenario_id": "01",
  "t1_monitor_ms": 1774168532260.8,
  "t2_analyze_ms": 1774168532283.2
}
```

**Response:**
```json
{
  "pod": "scenario-01-oom-heap",
  "diagnosis": "**Root Cause:** ...\n**Fix Command:**\n```bash\nkubectl ...\n```",
  "trace_id": "7ef6448f",
  "scenario_id": "01",
  "timestamps": {
    "t1_monitor_ms": 1774168532260.8,
    "t2_analyze_ms": 1774168532283.2,
    "t3_plan_ms": 1774168532301.2,
    "t4_execute_ms": 1774168539084.1,
    "mttr_ms": 6823.3
  }
}
```

### `GET /metrics`

Prometheus metrics endpoint. Scraped automatically by any Prometheus instance.

Key metrics:

| Metric | Type | Description |
|---|---|---|
| `KUBEWHISPER_diagnosis_requests_total` | Counter | Total requests by status (`success`/`error`) |
| `KUBEWHISPER_diagnosis_duration_seconds` | Histogram | End-to-end diagnosis latency |
| `KUBEWHISPER_rag_context_hits_total` | Counter | RAG retrieval hit/miss rate |
| `KUBEWHISPER_build_info` | Info | Version and model metadata |

### `GET /`

Health check. Returns `{"status": "neural_link_active"}`. No authentication required.

---

## Failure Dataset

`manifests/broken-scenarios/` contains 50 reproducible failure scenarios across three
categories. Each scenario has a corresponding entry in `dataset/manifest.json` with
ground truth labels for evaluation.

| Category | Scenarios | Count |
|---|---|---|
| Resource errors | OOMKilled, CPU throttle, ephemeral storage, probe failures, init container | 01–17 |
| Config errors | Missing secrets, bad image tags, wrong env vars, selector mismatches | 18–34 |
| Network / RBAC | ImagePullBackOff variants, DNS failure, RBAC denial, NetworkPolicy | 35–50 |

All 50 scenarios have `watchdog_resolves: false` — a simple restart loop will not fix
any of them. This establishes that KUBEWHISPER adds value beyond a basic liveness probe.

---

## Deployment

The system is deployable as two container images on any Kubernetes cluster.

### Build images

```bash
docker build -f Dockerfile.brain -t KUBEWHISPER-brain:latest .
docker build -f Dockerfile.agent -t KUBEWHISPER-agent:latest .
```

### Deploy to cluster

```bash
kubectl apply -f k8s/secret.yaml      # fill in base64-encoded keys first
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/brain-deployment.yaml
kubectl apply -f k8s/agent-daemonset.yaml
```

For Kind clusters, load images before deploying:
```bash
kind load docker-image KUBEWHISPER-brain:latest --name kubewhisper-lab
kind load docker-image KUBEWHISPER-agent:latest --name kubewhisper-lab
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `KUBEWHISPER_API_KEY` | Yes | — | Shared secret for `/analyze` auth |
| `DB_PATH` | No | `db_storage` | ChromaDB persistence path |
| `BRAIN_URL` | No | `http://localhost:8000/analyze` | Go agent target URL |
| `LIBRARIAN_CONFIG` | No | `config/sources.yaml` | Knowledge ingestion config |
| `MTTR_LOG_PATH` | No | `mttr_log.jsonl` | MTTR record output path |
| `SCENARIO_ID` | No | `unknown` | Set by benchmark runner per scenario |

---

## Development Phases

| Phase | Status | Description |
|---|---|---|
| 1 — Observer | Done | Manual baseline + automated log capture |
| 2 — Knowledge Base | Done | ChromaDB + `all-MiniLM-L6-v2` + Librarian ETL |
| 3 — Reasoner | Done | RAG pipeline + Gemini 2.5 Flash |
| 4 — Python Agent | Done | Autonomous MAPE-K loop in Python |
| 4.5 — Stabilization | Done | SDK migration + deduplication cache |
| 5 — Go Transition | Done | Compiled Go watcher + FastAPI Brain |
| 6 — Deployment | Done | Dockerfiles, Kubernetes manifests |
| 7 — Observability | Done | Prometheus metrics, JSON logging, circuit breaker |
| 8 — Dataset + MTTR | Done | 50-scenario dataset, per-stage timestamps |
| 9 — Schema Validation | In Progress | Pydantic validator, command allowlist, hallucination log |
| 10 — Benchmarking | Planned | 3-condition MTTR evaluation across all 50 scenarios |
| 11 — RAG vs Fine-tuned | Planned | Comparative evaluation + ablation study |
| 12 — Paper | Planned | Writeup and submission |

---

## Known Limitations

- Go agent hardcodes the `default` namespace. Cross-namespace support planned.
- Deduplication cache is in-memory and resets on agent restart.
- `db_storage/` must be pre-populated via `librarian.py`. An empty vector store causes
  Synapse to fall back to model-only knowledge with no RAG context.
- `mttr_log.jsonl` and `hallucination_log.jsonl` are gitignored — they contain runtime
  experiment data and must be preserved locally across benchmark runs.
- Baseline A MTTR (manual diagnosis) is simulated from published SRE incident reports,
  not measured directly. This is documented as a threat to validity in the paper.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
