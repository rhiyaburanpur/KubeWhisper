# Experiment 3.3 - 3.5: Inference Model Stabilization
**Date:** 2026-02-08
**Phase:** Phase 3 (The Reasoner)
**Subject:** Selection of Generative Backend under Rate Constraints

**1. The Selection Process (Exp 3.3)**
* **Initial Target:** `gemini-2.0-flash` (Selected for low latency).
* **Rationale:** The "Flash" series offers the optimal balance of speed and reasoning for SRE tasks.

**2. The Anomaly (Exp 3.4)**
* **Incident:** System encountered `429 Resource Exhausted` errors immediately.
* **Metric:** `generate_content_free_tier_requests` limit is 0 for the 2.0-preview tier.
* **Mitigation:** Implemented `tenacity` exponential backoff (2s -> 4s -> 8s) to handle transient failures.

**3. The Resolution (Exp 3.5)**
* **Failure:** Attempting to downgrade to `gemini-1.5-flash` resulted in `404 Not Found` due to API alias routing issues.
* **Correction:** Reconfigured Synapse to target `gemini-flash-latest`.
* **Outcome:** This alias provides a managed redirection to the currently available stable model, mitigating both quota issues (Preview tier) and availability issues (Version tags).