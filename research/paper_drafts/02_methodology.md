# 2. Methodology

## 2.1 System Architecture
We propose a hybrid **Neuro-Symbolic** architecture that decouples the observation layer from the reasoning layer. The system is composed of two primary subsystems:
1.  **The Agent (Symbolic Layer):** A lightweight, deterministic watcher responsible for real-time event detection and log extraction.
2.  **The Brain (Neural Layer):** A vector-based retrieval engine responsible for semantic analysis and context mapping.

## 2.2 The Vector Space Model (VSM)
To enable the system to "understand" error logs, we utilize high-dimensional vector embeddings.
* **Embedding Model:** We employ `all-MiniLM-L6-v2`, a pre-trained sentence transformer that maps text into a 384-dimensional vector space ($R^{384}$).
* **Vector Database:** Embeddings are stored in **ChromaDB**, utilizing Hierarchical Navigable Small World (HNSW) graphs for efficient approximate nearest neighbor (ANN) search.

## 2.3 Knowledge Ingestion Pipeline (The Librarian)
The efficacy of a Retrieval-Augmented Generation (RAG) system depends on the quality of its knowledge base. We implemented an automated ETL (Extract, Transform, Load) pipeline:
* **Extraction:** Unstructured HTML is scraped from official Kubernetes documentation.
* **Transformation:** Text is sanitized and segmented into fixed-size chunks (window size = 1000 characters) to preserve semantic context.
* **Loading:** Each chunk is encoded into a vector $v_i$ and indexed in the persistent store.

## 2.4 Semantic Search Algorithm
When a crash is detected, the error log $L$ is converted into a query vector $v_q$. The system then calculates the Cosine Similarity between $v_q$ and all stored knowledge vectors $v_k$:
$$Similarity(v_q, v_k) = \frac{v_q \cdot v_k}{||v_q|| \cdot ||v_k||}$$
The top-$k$ most similar documentation chunks are retrieved and forwarded to the reasoning engine.