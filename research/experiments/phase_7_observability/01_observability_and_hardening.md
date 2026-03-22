# Experiment Log: Phase 7 — Observability & Hardening

**Date:** March 2026
**Branch:** feat/phase-7-observability
**Status:** Complete

---

## 7.1 Objective

Phase 7 introduces three production-grade observability and resilience features to the
KUBEWHISPER system:

1. **Prometheus metrics** — structured counters and histograms exposed at `GET /metrics`
2. **Structured JSON logging with trace IDs** — machine-readable log lines correlated across
   the Go Agent and Python Brain via a shared `trace_id`
3. **Circuit breaker in the Go Agent** — automatic failure isolation when the Brain is
   unreachable

From a research perspective, the Prometheus instrumentation is the foundation for the MTTR
measurement methodology in Phase 8. Without timestamped, machine-readable duration data, the
>50% MTTR reduction claim cannot be supported with experimental evidence.

---

## 7.2 Changes Introduced

### `src/brain/metrics.py` (new)

Defines all Prometheus metric objects in a single module:

| Metric | Type | Description |
|---|---|---|
| `KUBEWHISPER_diagnosis_requests_total` | Counter | Total requests, labelled by `status` (`success` / `error`) |
| `KUBEWHISPER_diagnosis_duration_seconds` | Histogram | End-to-end diagnosis latency in seconds |
| `KUBEWHISPER_rag_context_hits_total` | Counter | RAG retrieval hit/miss count, labelled by `hit` (`true` / `false`) |
| `KUBEWHISPER_build_info` | Info | Static build metadata (version, model, embedding model) |

The histogram uses custom buckets (`0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0` seconds)
chosen to bracket the expected range of Gemini API response times under normal and rate-limited
conditions.

### `src/brain/server.py`

- Added `GET /metrics` endpoint returning `generate_latest()` in Prometheus text format
- `/analyze` now records `DIAGNOSIS_DURATION_SECONDS` using `time.monotonic()` around the full
  `brain.reason()` call
- Increments `DIAGNOSIS_REQUESTS_TOTAL` with `status="success"` or `status="error"` on
  every request
- `trace_id` (8-character prefix of `uuid4()`) is generated per request, included in all log
  lines, returned in the JSON response, and forwarded to the Brain as an `X-Trace-ID` HTTP
  header
- All `print()` calls replaced with `logJSON()` emitting structured JSON to stdout

### `src/brain/synapse.py`

- `reason()` return signature changed from `str` to `tuple[str, bool]`
- Second return value `rag_hit` is `True` if ChromaDB returned at least one context chunk,
  `False` if the model fell back to parametric knowledge only
- The server records `rag_hit` in `RAG_CONTEXT_HITS_TOTAL` and includes it in the diagnosis
  log line

### `src/go-agent/main.go`

- All `fmt.Printf` calls replaced with `logJSON()` emitting structured JSON:
  `{"level":"...","service":"go-agent","msg":"...","pod":"...","trace_id":"..."}`
- `trace_id` is derived from the nanosecond Unix timestamp at request time and forwarded as
  `X-Trace-ID` on every HTTP POST to the Brain
- Circuit breaker implemented as a `circuitBreaker` struct with three states:
  - `closed` — normal operation
  - `open` — brain declared unreachable after 3 consecutive failures; requests blocked for
    30 seconds
  - `half-open` — one probe request allowed after cooldown to test recovery
- Deduplication cache mutex upgraded to `sync.Mutex` for correctness under concurrent events

---

## 7.3 Verification Results

System verified end-to-end on Kind cluster (`kubewhisper-lab`) with pod `bad-student`
(`manifests/broken-scenarios/crash.yaml`).

### Brain startup (JSON logging confirmed)
```
{"level": "info", "service": "brain", "msg": "Loading Synapse model..."}
{"level": "info", "service": "brain", "msg": "Brain online."}
```

### Go Agent startup (JSON logging confirmed)
```
{"level":"info","service":"go-agent","msg":"KUBEWHISPER Go-Agent starting"}
{"level":"info","service":"go-agent","msg":"Watching for CrashLoopBackOff and ImagePullBackOff events"}
```

### Crash detection and trace ID correlation
```
Agent:  {"level":"warn","service":"go-agent","msg":"Crash detected: CrashLoopBackOff","pod":"bad-student"}
Agent:  {"level":"info","service":"go-agent","msg":"Sending crash report to brain","pod":"bad-student","trace_id":"d4d7b17b"}
Brain:  {"level":"info","service":"brain","msg":"Crash report received","trace_id":"d4d7b17b","pod":"bad-student"}
Brain:  {"level":"info","service":"brain","msg":"Diagnosis complete","trace_id":"d4d7b17b","pod":"bad-student","duration_seconds":9.882,"rag_hit":true}
Agent:  {"level":"info","service":"go-agent","msg":"Diagnosis received","pod":"bad-student","trace_id":"d4d7b17b"}
```

The `trace_id` value `d4d7b17b` is identical across both processes, confirming end-to-end
request correlation.

### Metrics endpoint sample (after one successful diagnosis)
```
KUBEWHISPER_build_info{embedding_model="all-MiniLM-L6-v2",model="gemini-2.5-flash",version="0.7.0"} 1.0
KUBEWHISPER_diagnosis_requests_total{status="success"} 1.0
KUBEWHISPER_diagnosis_requests_total{status="error"} 0.0
KUBEWHISPER_diagnosis_duration_seconds_bucket{le="10.0"} 1.0
KUBEWHISPER_diagnosis_duration_seconds_sum 9.882
KUBEWHISPER_rag_context_hits_total{hit="true"} 1.0
KUBEWHISPER_rag_context_hits_total{hit="false"} 0.0
```

### Observed latency
End-to-end diagnosis duration: **9.882 seconds** (dominated by Gemini API call latency).
This establishes the baseline for the RAG-augmented pipeline under non-rate-limited conditions.
Manual baseline from Phase 1 was **60+ seconds**. The Phase 7 instrumentation will be used in
Phase 8 to produce statistically valid MTTR measurements across the full 50-scenario dataset.

---

## 7.4 Relevance to Research Paper

This phase directly enables the paper's quantitative evaluation methodology:

- `KUBEWHISPER_diagnosis_duration_seconds` provides the raw latency data for the MTTR
  comparison table in the Results section
- `KUBEWHISPER_rag_context_hits_total` provides the RAG retrieval rate, which will be
  reported alongside accuracy to characterise knowledge base coverage
- `KUBEWHISPER_diagnosis_requests_total{status="error"}` feeds into the hallucination
  rate calculation once the Pydantic schema validator is introduced in Phase 9
- The `trace_id` correlation mechanism enables per-incident audit trails, which are required
  for the Gold Standard dataset annotation process in Phase 8

---

## 7.5 Known Limitations

- `duration_seconds` includes Gemini API network latency, which varies by region and load.
  Phase 8 will record a minimum of 50 samples to compute a stable mean and standard deviation.
- The circuit breaker cooldown (30 seconds) and failure threshold (3 attempts) are currently
  hardcoded. These will be made configurable via environment variables in a future hardening
  pass.
- Prometheus metrics are not yet scraped by an in-cluster Prometheus instance. For the local
  evaluation in Phases 8–10, metrics will be read directly from `GET /metrics` after each
  test run.