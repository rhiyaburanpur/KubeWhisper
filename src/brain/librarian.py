import requests
import yaml
import os
from bs4 import BeautifulSoup
from src.brain.memory import KnowledgeBase

# FIX: Config file path is configurable via env var
CONFIG_PATH = os.getenv("LIBRARIAN_CONFIG", "config/sources.yaml")

def load_sources(config_path):
    """Load ingestion sources from a YAML config file."""
    print(f" [librarian] Loading sources from: {config_path}")
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config.get("sources", [])
    except FileNotFoundError:
        print(f" [!] Config file not found: {config_path}")
        return []
    except yaml.YAMLError as e:
        print(f" [!] YAML parse error: {e}")
        return []

def fetch_docs(url):
    print(f" [librarian] Fetching: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        content_div = (
            soup.find('main') or
            soup.find('article') or
            soup.find('div', {'id': 'docsContent'})
        )
        return content_div.get_text(separator="\n") if content_div else soup.get_text()
    except Exception as e:
        print(f" [!] Error fetching {url}: {e}")
        return None

def chunk_text(text, chunk_size=1000):
    chunks = []
    clean_text = " ".join(text.split())
    for i in range(0, len(clean_text), chunk_size):
        chunks.append(clean_text[i:i + chunk_size])
    return chunks

def main():
    print(" [librarian] Starting Ingestion Cycle...")
    kb = KnowledgeBase()

    sources = load_sources(CONFIG_PATH)
    if not sources:
        print(" [!] No sources found. Aborting.")
        return

    total_chunks = 0
    for source in sources:
        url = source.get("url")
        doc_type = source.get("type", "docs")

        if not url:
            print(" [!] Skipping source with no URL.")
            continue

        raw_text = fetch_docs(url)
        if not raw_text:
            print(f" [!] Skipping {url}: No content retrieved.")
            continue

        chunks = chunk_text(raw_text)
        metadatas = [{"source": url, "type": doc_type} for _ in chunks]
        kb.learn(text_snippets=chunks, metadata_list=metadatas)
        total_chunks += len(chunks)
        print(f" [librarian] Ingested {len(chunks)} chunks from {url}")

    print(f" [librarian] Ingestion Complete. Total chunks: {total_chunks}")

if __name__ == "__main__":
    main()