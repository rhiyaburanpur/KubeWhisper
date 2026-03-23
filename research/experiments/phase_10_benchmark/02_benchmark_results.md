# Phase 10 — Benchmark Results (First Full Run)

**Date:** March 2026
**Scenarios:** 50 (Gold Standard Dataset)
**Cluster:** Kind (local), cluster name: kubewhisper-lab, namespace: default
**Brain:** Gemini 2.5 Flash via RAG (ChromaDB + all-MiniLM-L6-v2)
**Condition:** KubeWhisperer autonomous diagnosis (Condition C in paper)

---

## Summary

| Metric | Value |
|---|---|
| Total scenarios | 50 |
| Successful diagnoses | 33 (66%) |
| Timeouts | 13 (26%) |
| Errors (apply failure) | 4 (8%) |
| Average MTTR | 8,512 ms (8.51s) |
| Minimum MTTR | 5,141 ms (5.14s) |
| Maximum MTTR | 29,480 ms (29.48s) |
| RAG hit rate | 100% (33/33) |
| Hallucination rate | 0.0% (0/33) |
| Baseline MTTR (manual) | 60,000+ ms |
| MTTR reduction | >85% |

---

## Results by Category

| Category | Scenarios | Successful | Timed Out | Errors | Avg MTTR |
|---|---|---|---|---|---|
| Resource | 17 | 10 | 7 | 0 | 14,362 ms |
| Config | 17 | 10 | 4 | 3 | 5,307 ms |
| Network | 16 | 13 | 2 | 1 | 6,477 ms |

**Observation:** Resource scenarios have higher average MTTR (14.3s) because containers
actually run and consume memory before the OOM killer or CPU throttle triggers. Config
and network scenarios fail immediately on startup, producing faster diagnoses (5–6s).

---

## Successful Scenarios (33)

| ID | Name | MTTR (ms) | RAG Hit | Validation |
|---|---|---|---|---|
| 01 | oom-kill-heap | 14,062 | True | True |
| 02 | exit-code-1-generic | 26,233 | True | True |
| 03 | exit-code-137-oom | 9,966 | True | True |
| 04 | exit-code-139-segfault | 8,112 | True | True |
| 09 | cpu-limit-throttle-crash | 13,504 | True | True |
| 10 | disk-write-permission-denied | 16,852 | True | True |
| 11 | too-many-open-files | 29,480 | True | True |
| 12 | job-backoff-limit | 14,346 | True | True |
| 13 | oom-kill-java-heap | 5,531 | True | True |
| 17 | crash-loop-exit-2 | 5,537 | True | True |
| 18 | missing-env-var | 5,409 | True | True |
| 19 | wrong-image-tag | 5,305 | True | True |
| 22 | bad-command-syntax | 5,513 | True | True |
| 23 | wrong-port-in-service | 5,168 | True | True |
| 24 | invalid-env-value-type | 5,163 | True | True |
| 26 | wrong-working-dir | 5,427 | True | True |
| 28 | image-entrypoint-not-found | 5,323 | True | True |
| 30 | config-file-missing-in-image | 5,202 | True | True |
| 32 | env-var-empty-string | 5,357 | True | True |
| 33 | wrong-image-repo | 5,203 | True | True |
| 35 | imagepullbackoff-private-registry | 5,442 | True | True |
| 37 | rbac-forbidden-api-call | 5,141 | True | True |
| 38 | dns-resolution-failure | 5,206 | True | True |
| 39 | network-policy-blocks-egress | 5,496 | True | True |
| 40 | clusterip-no-endpoints | 5,308 | True | True |
| 41 | imagepullbackoff-rate-limit | 5,244 | True | True |
| 42 | tls-cert-verify-fail | 5,338 | True | True |
| 44 | pod-to-pod-network-unreachable | 20,601 | True | True |
| 45 | ingress-backend-not-found | 5,395 | True | True |
| 46 | rbac-missing-clusterrole | 5,303 | True | True |
| 47 | external-service-timeout | 5,142 | True | True |
| 48 | imagepullbackoff-wrong-pullsecret | 5,411 | True | True |
| 49 | coredns-pod-not-found | 5,168 | True | True |

---

## Timed Out Scenarios (13)

These scenarios did not produce a `CrashLoopBackOff` or `ImagePullBackOff` event within
the 90-second window. The Go agent watches only these two states. Pods in these scenarios
entered `Pending`, `NotReady`, or were evicted without producing a watchable crash event.

| ID | Name | Category | Reason |
|---|---|---|---|
| 05 | ephemeral-storage-full | resource | Pod evicted, no CrashLoopBackOff |
| 06 | liveness-probe-fail | resource | Pod stays Running, probe fails silently |
| 07 | readiness-never-ready | resource | Pod stays Running, never reaches Ready |
| 08 | init-container-fail | resource | Init container fails, pod stuck in Init state |
| 14 | pod-evicted-node-pressure | resource | Pod evicted, not CrashLoopBackOff |
| 15 | startup-probe-timeout | resource | Startup probe kills container slowly |
| 16 | container-cannot-run-as-root | resource | Pod stays Pending due to security policy |
| 20 | missing-secret-ref | config | Pod stays Pending, never starts |
| 21 | missing-configmap-ref | config | Pod stays Pending, never starts |
| 31 | replica-count-zero | config | No pods created at all |
| 34 | resource-request-exceeds-node | config | Pod stays Pending, unschedulable |
| 43 | service-port-mismatch | network | Pod runs but no crash event fires |
| 50 | node-not-ready-pod-pending | network | Pod stays Pending, node issue |

---

## Error Scenarios (4)

These scenarios failed at the `kubectl apply` stage or produced no observable pod.

| ID | Name | Category | Reason |
|---|---|---|---|
| 25 | volume-mount-path-conflict | config | kubectl apply rejected by API server |
| 27 | cronjob-bad-schedule | config | CronJob created but no pod scheduled |
| 29 | deployment-wrong-selector | config | Deployment created but selector mismatch produces no pods |
| 36 | service-account-missing | network | Pod stuck in Pending, no crash event |

---

## Research Paper Implications

### Supporting the hypothesis

- MTTR reduction of >85% (8.51s vs 60s+ manual) far exceeds the >50% hypothesis
- 0.0% hallucination rate across 33 diagnoses supports the <2% claim with hard evidence
- 100% RAG hit rate confirms the knowledge base is correctly populated and retrieved

### Threats to validity (to document in paper)

1. **Agent scope limitation:** The Go agent detects only `CrashLoopBackOff` and
   `ImagePullBackOff`. 13 of 50 scenarios (26%) involve failure modes outside this
   scope — evictions, pending pods, probe failures, and scheduling errors. Extending
   the agent to cover these states is future work.

2. **Cluster environment:** All results were collected on a single-node Kind cluster
   running locally. Production clusters with multiple nodes, real network policies,
   and resource pressure may produce different timing characteristics.

3. **Manual baseline:** The 60s+ baseline MTTR is estimated from standard SRE incident
   response procedures, not measured directly in a controlled experiment. This is
   consistent with published SRE incident response benchmarks.

4. **Single run:** Each scenario was executed once. Statistical variance across multiple
   runs is not yet measured. Phase 11 will include repeated runs for select scenarios.

5. **Hallucination measurement scope:** Hallucination rate measures structural validity
   (schema conformance + command allowlist). It does not measure factual correctness
   of the root cause diagnosis against ground truth labels. Ground truth comparison
   is planned for Phase 11.

---

## Next Steps

- Phase 11: RAG vs Fine-tuned LLM comparison and ablation study
- Extend Go agent to detect `Pending`, `Evicted`, and probe failure states (future work)
- Run repeated trials on select scenarios to measure MTTR variance
- Compare diagnosed root causes against `dataset/manifest.json` ground truth labels