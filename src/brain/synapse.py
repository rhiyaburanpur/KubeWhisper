import os
from google import genai
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from src.brain.memory import KnowledgeBase


class Synapse:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable not set.")

        self.client = genai.Client(api_key=self.api_key)
        self.model_id = "models/gemini-2.5-flash"

        db_path = os.getenv("DB_PATH", "db_storage")
        self.memory = KnowledgeBase(persistence_path=db_path)
        print(f" [synapse] Neuro-Symbolic Link Established (Model: {self.model_id}).")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _ask_gemini(self, prompt):
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f" [synapse] API Error Details: {e}")
            raise

    def reason(self, error_log):
        """
        Runs the RAG pipeline and returns a (diagnosis, rag_hit) tuple.
        rag_hit is True if the vector store returned at least one context chunk.
        """
        print(" [synapse] Retrieving relevant knowledge...")
        context = self.memory.recall(error_log, n_results=1)

        rag_hit = bool(context and context[0])

        if not rag_hit:
            context_text = "No relevant documentation found in knowledge base."
            print(" [synapse] No context found. Relying on model knowledge.")
        else:
            context_text = context[0]
            print(f" [synapse] Retrieved context: {context_text[:100]}...")

        prompt = f"""You are a Kubernetes Site Reliability Engineer (SRE) with deep expertise in container orchestration and debugging.

**Knowledge Base Context:**
{context_text}

**Real-time Error Log:**
{error_log}

**Your Task:**
Analyze this crash and provide:
1. **Root Cause** (one clear sentence explaining what happened)
2. **Fix Command** (the exact `kubectl` command to resolve this issue)

Format as:
**Root Cause:** [explanation]
**Fix Command:**
```bash
[command here]
```
"""
        print(" [synapse] Consulting Gemini AI...")
        try:
            diagnosis = self._ask_gemini(prompt)
            print(" [synapse] Analysis complete.")
            return diagnosis, rag_hit
        except Exception as e:
            error_msg = (
                f"AI Analysis Failed: {type(e).__name__}\n\n"
                f"Fallback: Unable to generate AI diagnosis. Investigate manually:\n"
                f"1. Check logs:      kubectl logs <pod-name> --previous\n"
                f"2. Inspect pod:     kubectl describe pod <pod-name>\n"
                f"3. Cluster events:  kubectl get events --sort-by='.lastTimestamp'\n"
                f"4. Resource usage:  kubectl top pod <pod-name>"
            )
            print(f" [synapse] ERROR: {e}")
            return error_msg, rag_hit