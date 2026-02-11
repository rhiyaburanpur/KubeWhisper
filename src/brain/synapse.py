import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from src.brain.memory import KnowledgeBase

class Synapse:
    """
    The Reasoning Layer (v2).
    Migrated to use the modern `google-genai` SDK for stability.
    """
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable not set.")
        
        # MIGRATION: New Client Initialization
        self.client = genai.Client(api_key=self.api_key)
        
        # We use 'gemini-1.5-flash' as the stable workhorse
        # CORRECTED: Must include the full model path
        self.model_id = 'models/gemini-2.5-flash'
        
        self.memory = KnowledgeBase(persistence_path="db_storage")
        print(f" [synapse] Neuro-Symbolic Link Established (Model: {self.model_id}).")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _ask_gemini(self, prompt):
        """
        CORRECTED: New Google GenAI SDK syntax
        
        The `google-genai` package uses a different API structure:
        1. Model path must be 'models/gemini-1.5-flash' (not just 'gemini-1.5-flash')
        2. Contents must be a list of Content objects or strings
        3. Response object has .text property
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt  # Can be a string or types.Content object
            )
            return response.text
        except Exception as e:
            print(f" [synapse] API Error Details: {e}")
            raise

    def reason(self, error_log):
        """
        The RAG pipeline: Retrieval → Augmentation → Generation
        """
        # Step 1: Retrieval (RAG)
        print(" [synapse] Retrieving relevant knowledge...")
        context = self.memory.recall(error_log, n_results=1)
        
        if not context or not context[0]:
            context_text = "No relevant documentation found in knowledge base."
            print(" [synapse] No context found. Relying on model knowledge.")
        else:
            context_text = context[0]
            print(f" [synapse] Retrieved context: {context_text[:100]}...")

        # Step 2: Augmentation (The Prompt Engineering)
        prompt = f"""You are a Kubernetes Site Reliability Engineer (SRE) with deep expertise in container orchestration and debugging.

**Knowledge Base Context:**
{context_text}

**Real-time Error Log:**
{error_log}

**Your Task:**
Analyze this crash and provide:

1. **Root Cause** (one clear sentence explaining what happened)
2. **Fix Command** (the exact `kubectl` command to resolve this issue)

Keep your response concise and actionable. Format as:

**Root Cause:** [explanation]
**Fix Command:**
```bash
[command here]
```
"""
        
        # Step 3: Generation
        print(" [synapse] Consulting Gemini AI...")
        try:
            diagnosis = self._ask_gemini(prompt)
            print(" [synapse] Analysis complete.")
            return diagnosis
        except Exception as e:
            error_msg = f"⚠️ AI Analysis Failed: {type(e).__name__}\n\nFallback: This appears to be a CrashLoopBackOff. Check:\n1. Container logs: kubectl logs <pod-name> --previous\n2. Resource limits: kubectl describe pod <pod-name>\n3. Image availability: kubectl get events"
            print(f" [synapse] ERROR: {e}")
            return error_msg

if __name__ == "__main__":
    print("=== SYNAPSE SELF-TEST ===\n")
    bot = Synapse()
    
    test_log = "Pod status is CrashLoopBackOff. Exit Code 137. OOMKilled."
    print(f"Test Query: {test_log}\n")
    
    result = bot.reason(test_log)
    print("\n=== DIAGNOSIS ===")
    print(result)