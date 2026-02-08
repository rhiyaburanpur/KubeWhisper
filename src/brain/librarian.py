import requests
from bs4 import BeautifulSoup
from src.brain.memory import KnowledgeBase

# Target: Official Kubernetes Debugging Guide
K8S_DEBUG_URL = "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/"

def fetch_docs(url):
    print(f" [librarian] Fetching: {url}")
    try:
        # 1. Extract
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Kubernetes docs store content in <main>, <article>, or specific div IDs
        content_div = soup.find('main') or soup.find('article') or soup.find('div', {'id': 'docsContent'})
        
        if not content_div:
            return soup.get_text()
            
        return content_div.get_text(separator="\n")
    except Exception as e:
        print(f" [!] Error fetching docs: {e}")
        return None

def chunk_text(text, chunk_size=1000):
    # 2. Transform
    # Vectors lose meaning if text is too long. We split into 1000-char chunks.
    chunks = []
    clean_text = " ".join(text.split())
    
    for i in range(0, len(clean_text), chunk_size):
        chunks.append(clean_text[i:i + chunk_size])
    return chunks

def main():
    print(" [librarian] Starting Ingestion Cycle...")
    
    # Connect to the existing Brain
    kb = KnowledgeBase(persistence_path="db_storage")
    
    # Execute ETL
    raw_text = fetch_docs(K8S_DEBUG_URL)
    if not raw_text:
        print(" [!] Aborting: No content retrieved.")
        return

    chunks = chunk_text(raw_text)
    print(f" [librarian] Generated {len(chunks)} knowledge chunks.")
    
    # 3. Load
    # Metadata helps us cite sources later -> Anti-Hallucination
    metadatas = [{"source": K8S_DEBUG_URL, "type": "official_docs"} for _ in chunks]
    
    kb.learn(
        text_snippets=chunks,
        metadata_list=metadatas
    )
    print(" [librarian] Ingestion Complete.")

if __name__ == "__main__":
    main()