import chromadb
from chromadb.utils import embedding_functions
import uuid
import os

class KnowledgeBase:
    """
    The Long-Term Memory of KubeWhisperer.
    
    Responsibility: 
    1. Manage the Vector Database (ChromaDB).
    2. Convert text (logs/docs) into Vector Embeddings.
    3. Perform Semantic Search (RAG).
    """
    
    def __init__(self, persistence_path="db_storage"):
        """
        Initialize the ChromaDB client.
        
        Args:
            persistence_path (str): Folder where memory is saved.
        """
        print(f" [brain] Initializing Memory at '{persistence_path}'...")

        if not os.path.exists(persistence_path):
            os.makedirs(persistence_path)

        try:
            self.client = chromadb.PersistentClient(path=persistence_path)
            
            # We use the 'all-MiniLM-L6-v2' model. 
            # It maps sentences to a 384 dimensional dense vector space.

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
        """
        Ingests information into the vector store.
        
        Args:
            text_snippets (list): The raw text to learn.
            metadata_list (list): Context (e.g., {"source": "k8s_docs"}).
        """
        # Generate unique IDs for each snippet
        ids = [str(uuid.uuid4()) for _ in text_snippets]
        
        self.collection.add(
            documents=text_snippets,
            ids=ids,
            metadatas=metadata_list
        )
        print(f" [brain] Learned {len(text_snippets)} new concepts.")

    def recall(self, query_text, n_results=1):
        """
        Performs a Semantic Search.
        
        Args:
            query_text (str): The question (e.g., "What is OOMKilled?").
            n_results (int): How many matches to return.
            
        Returns:
            list: The most relevant text snippets.
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )

        if results['documents']:
            return results['documents'][0]
        return []

# Runs only if you execute this file directly
if __name__ == "__main__":
    print("SELF-DIAGNOSTIC MODE")
    kb = KnowledgeBase()
    
    # 1. Teach
    print("\n[Step 1] Ingesting test data...")
    kb.learn(
        text_snippets=["OOMKilled means Out Of Memory. It happens when a container uses more RAM than allowed."],
        metadata_list=[{"tag": "memory_error"}]
    )
    
    # 2. Test
    query = "Why did my pod die from memory issues?"
    print(f"\n[Step 2] Testing Semantic Recall...")
    print(f"Query: {query}")
    answer = kb.recall(query)
    print(f"Retrieved Answer: {answer[0]}")
    print("\n[✓] Diagnostic Complete. System Ready.")