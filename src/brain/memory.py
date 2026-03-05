import chromadb
from chromadb.utils import embedding_functions
import uuid
import os

class KnowledgeBase:
    def __init__(self, persistence_path=None):
        # FIX: Resolve path from env var if not explicitly passed
        if persistence_path is None:
            persistence_path = os.getenv("DB_PATH", "db_storage")

        print(f" [brain] Initializing Memory at '{persistence_path}'...")
        os.makedirs(persistence_path, exist_ok=True)

        try:
            self.client = chromadb.PersistentClient(path=persistence_path)
            self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.get_or_create_collection(
                name="k8s_knowledge",
                embedding_function=self.embedding_fn
            )
            print(" [brain] Memory Cortex Online.")
        except Exception as e:
            print(f" [!] CRITICAL: Memory Failure: {e}")
            raise e

    def learn(self, text_snippets, metadata_list):
        ids = [str(uuid.uuid4()) for _ in text_snippets]
        self.collection.add(
            documents=text_snippets,
            ids=ids,
            metadatas=metadata_list
        )
        print(f" [brain] Learned {len(text_snippets)} new concepts.")

    def recall(self, query_text, n_results=1):
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        if results['documents']:
            return results['documents'][0]
        return []