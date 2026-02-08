# Experiment 2.3: Knowledge Ingestion (The Librarian)
**Date:** 2026-02-08
**Phase:** Phase 2 (The Knowledge Base)
**Subject:** ETL Pipeline for Unstructured Documentation

**1. Methodology**
To enable RAG, the system must ingest unstructured technical documentation.

**2. The Pipeline**
* **Source:** Official Kubernetes Documentation (Web).
* **Extraction:** `requests` + `BeautifulSoup`.
* **Transformation:** Fixed-window segmentation (1000 chars).
* **Loading:** `chromadb` (Persistent Vector Store).

**3. Execution Nuance**
The scraper is structured as a package submodule. Execution requires the `-m` flag (`python -m src.brain.librarian`) to resolve the relative imports of the `KnowledgeBase` class correctly.

**4. Outcome**
The pipeline successfully scraped the target URL, generating embeddings via `all-MiniLM-L6-v2`. The vector store now contains a searchable index of Kubernetes debugging strategies.