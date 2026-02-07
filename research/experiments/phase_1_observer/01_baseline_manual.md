# Experiment 01: Baseline Manual Observation
**Date:** 2026-02-07
**Subject:** Manual detection of Pod Failure 

**1. Setup**
* Created a standard Kubernetes Cluster using Kind.
* Deployed a "fragile" pod (`crash.yaml`) designed to fail after 10 seconds.
* Command used: `kubectl apply -f manifests/broken-scenarios/crash.yaml`

**2. Observations (The Timeline)**

1. Deployed 'bad-student' pod.
2. Status started as 'Running'.
3. After approx 15 seconds, status changed to 'Error'.
4. Kubernetes automatically restarted the pod (Restart Count: 1).
5. Pod entered 'CrashLoopBackOff' state.


**3. The Limitation (Research Finding)**
* Kubernetes successfully detected the crash (State change).
* Kubernetes successfully attempted a restart (Loop).
* **CRITICAL GAP:** Kubernetes did NOT analyze *why* it crashed. It only blindly restarted it.
* **Hypothesis:** An external observer (KubeWhisperer) is required to intercept the `Error` state and extract logs before the restart loop obscures the root cause.