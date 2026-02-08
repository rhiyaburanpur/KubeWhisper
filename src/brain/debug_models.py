import os
import google.generativeai as genai
from dotenv import load_dotenv

def list_available_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print(" [!] Error: API Key not found in .env")
        return

    genai.configure(api_key=api_key)
    
    print(" [?] Querying Google for available models...")
    try:
        # Iterate through all available models
        for m in genai.list_models():
            # We only care about models that can generate content (chat)
            if 'generateContent' in m.supported_generation_methods:
                print(f"  - {m.name}")
    except Exception as e:
        print(f" [!] Error contacting Google API: {e}")

if __name__ == "__main__":
    list_available_models()