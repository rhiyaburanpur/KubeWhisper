from prometheus_client import Counter, Histogram, Info

DIAGNOSIS_REQUESTS_TOTAL = Counter(
    "kubewhisperer_diagnosis_requests_total",
    "Total number of diagnosis requests received",
    ["status"],
)

DIAGNOSIS_DURATION_SECONDS = Histogram(
    "kubewhisperer_diagnosis_duration_seconds",
    "End-to-end time in seconds to produce a diagnosis",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

RAG_CONTEXT_HITS_TOTAL = Counter(
    "kubewhisperer_rag_context_hits_total",
    "Number of diagnosis requests where RAG retrieved at least one context chunk",
    ["hit"],
)

BUILD_INFO = Info(
    "kubewhisperer_build",
    "Static build metadata for the KubeWhisperer Brain",
)

BUILD_INFO.info({
    "version": "0.7.0",
    "model": "gemini-2.5-flash",
    "embedding_model": "all-MiniLM-L6-v2",
})