# Title: KubeWhisperer: A MAPE-K Approach to Autonomic Container Orchestration using Large Language Models

## Abstract

**Context:**
Modern cloud-native environments generate vast amounts of log data, making manual debugging of microservices increasingly complex, time-consuming, and error-prone.

**Problem:**
Traditional observability tools like Prometheus and Grafana provide metrics but lack the semantic understanding that is required fro identifying the root cause of failures, directly contributing to a high Mean Time to Recovery (MTTR).

**Solution:**
We propose **KubeWhisperer**, an autonomic system that integrates the MAPE-K feedback loop with a Vector Space Model (VSM). This hybrid architecture automatically intercepts failure signals and retrieves context-aware solutions from technical documentation, effectively closing the loop between detection and diagnosis.

**Results:**
Preliminary experiments demonstrate that our approach reduces diagnosis latency from >60 seconds (manual baseline) to <1 second (automated capture), eliminating the discovery gap in transient pod failures.

**Keywords:**
Kubernetes, AIOps, Large Language Models, Autonomic Computing, MAPE-K.