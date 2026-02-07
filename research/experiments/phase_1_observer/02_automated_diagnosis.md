# Experiment 02: Automated Log Retrieval
**Date:** 2026-02-07
**Subject:** Automated Extraction of Failure Context

**1. Setup**
* Tool: KubeWhisperer (Observer Module v1.5)
* Target: Pod 'bad-student' (Simulated Memory Leak)
* Constraint: No human intervention allowed during the crash window.

**2. Observations**
* **Detection:** Observer successfully intercepted the `CrashLoopBackOff` event.
* **Action:** Diagnostician module triggered `get_pod_logs()`.
* **Result:** Successfully captured the critical signature: `CRITICAL: Application failed to allocate memory.`

**3. Comparison to Baseline**
* **Manual (Exp 01):** Required operator to notice crash -> run `kubectl get pods` -> run `kubectl logs`. Time est: >60s.
* **Automated (Exp 02):** Log context captured instantly upon detection signal. Time est: <1s.

**Conclusion:**
The "Diagnostician" module successfully eliminates the "Discovery Latency" gap. The system now possesses the raw text required for LLM analysis.