# 3. Implementation

## 3.1 The Observer (Go Agent)
The cluster observer is implemented as a compiled Go binary using the `client-go` library to
watch the Kubernetes API server event stream directly. This replaced an earlier Python-based
watcher (Phase 4) for two reasons: the compiled binary runs at approximately 8MB resident
memory versus 100MB+ for the Python interpreter, and Go's native concurrency model handles
bursty event streams without blocking.

The agent filters `MODIFIED` pod events and checks each container status for `CrashLoopBackOff`
or `ImagePullBackOff` waiting states. On detection, it fetches the last 50 lines of the previous
container's logs via the Kubernetes log API and POSTs a structured crash report to the Python
Brain over HTTP.

**Deduplication:** An in-memory TTL cache tracks `pod_name` to `last_diagnosed_at` timestamp.
Duplicate diagnosis requests for the same pod are suppressed for 300 seconds. In persistent
crash loop scenarios this reduced outbound API calls by approximately 90%.

**Authentication:** The Go agent and Python Brain share a secret (`KUBEWHISPERER_API_KEY`)
transmitted as an `X-API-Key` HTTP header on every `/analyze` request. The brain rejects
requests with missing or incorrect keys with HTTP 403.

## 3.2 The Reasoner (Python Brain)
The reasoning core is exposed as a FastAPI server and integrates a retrieval pipeline with a
generative model.

**RAG Pipeline:** On each request, the Synapse module queries ChromaDB using cosine similarity
over 384-dimensional `all-MiniLM-L6-v2` embeddings to retrieve the most relevant documentation
chunk. This chunk is prepended to the Gemini prompt as grounding context, reducing the model's
reliance on parametric knowledge for Kubernetes-specific failure modes.

**Inference Engine:** We use Google Gemini 2.5 Flash via the `google-genai` SDK. The model
was selected for sub-second inference latency on structured reasoning tasks. All API calls are
wrapped in exponential backoff (`tenacity`, 2s → 4s → 8s) to handle transient 429 rate limit
errors.

**Prompt Structure:** The prompt instructs the model to produce exactly two fields — Root Cause
(one sentence) and Fix Command (one `kubectl` command in a fenced code block). This constrained
output format is the precondition for the schema validation layer introduced in Phase 9.

## 3.3 Knowledge Base
Documentation is ingested via `librarian.py`, an ETL pipeline that scrapes configured URLs,
chunks content into 1000-character windows, embeds each chunk using `all-MiniLM-L6-v2`, and
persists the vectors in a ChromaDB `PersistentClient` store. The ingestion source list is
externalized to `config/sources.yaml` and configurable without code changes.

## 3.4 Security and Configuration
Adhering to 12-Factor App principles, all credentials and environment-specific values are
injected via environment variables and never committed to version control. The `.env.example`
file documents every variable with generation instructions. In the in-cluster deployment, secrets
are managed via Kubernetes Secret objects and mounted into pods at runtime — the application
code reads them identically whether running locally or inside the cluster.

## 3.5 Deployment Architecture
The system is packaged as two container images for reproducible deployment. The Python Brain
is built on `python:3.12-slim` and exposed as a Kubernetes Deployment with a `readinessProbe`
on the health endpoint, ensuring the RAG pipeline is fully initialized before traffic is
accepted. The Go Agent is built using a two-stage Docker build: a `golang:1.25` builder stage
compiles a statically linked binary (`CGO_ENABLED=0`), which is then copied into a
`distroless/static` final image with no shell or package manager, producing a final image under
10MB. The agent runs as a Kubernetes DaemonSet with a minimal RBAC ClusterRole granting only
`get`, `list`, and `watch` on pods and pod logs. All Kubernetes manifests, Dockerfiles, and a
Secret template are included in the repository under `k8s/`.