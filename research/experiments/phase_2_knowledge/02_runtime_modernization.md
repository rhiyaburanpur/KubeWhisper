# Experiment 03: Python 3.13 Runtime Modernization
**Date:** 2026-02-08
**Phase:** Phase 2 (The Knowledge Base)
**Subject:** Resolution of Transitive Dependency Conflicts in Neuro-Symbolic Stack

**1. The Anomaly**
Despite attempting to upgrade the stack, the runtime continued to crash with `RuntimeWarning: invalid value encountered in exp2` and ABI inconsistencies.

**2. Root Cause Analysis (RCA)**
* **Observation:** Installation logs showed `Requirement already satisfied: sentence-transformers==2.2.2`.
* **Conflict:** The stale `sentence-transformers` library (v2.x) contains a hard constraint for `numpy<2.0`. This forced the package manager to downgrade `numpy` to `1.26.4`, which is binary-incompatible with Python 3.13 on Windows (VS C++ runtime mismatch).

**3. Corrective Action**
Executed a targeted `--force-reinstall` of the logic layer to align ABI compatibility:
* `sentence-transformers >= 3.2.0` (Unlocks Numpy 2.0 support).
* `numpy >= 2.1.0` (Native Python 3.13 ABI support).

**4. Conclusion**
For systems research on bleeding-edge runtimes (Python 3.13), legacy AI libraries effectively act as "poison pills." Strict version pinning is required to prevent transitive downgrades.
* **Final Stack:** ChromaDB 0.5.5, Sentence-Transformers 3.2.0, Numpy 2.1.0.