import os
import google.generativeai as genai
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from src.brain.memory import KnowledgeBase

class Synapse:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY not set.")
        
        genai.configure(api_key=self.api_key)
        
        # FIX: Using the alias 'gemini-flash-latest'
        # This resolves to the current stable Flash model available to your key
        # avoiding 404s on specific versions like 1.5-flash
        self.model = genai.GenerativeModel('gemini-flash-latest')
        
        self.memory = KnowledgeBase(persistence_path="db_storage")
        print(" [synapse] Neuro-Symbolic Link Established (Model: gemini-flash-latest).")

    # Retry logic: 3 attempts, exponential backoff
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _ask_gemini(self, prompt):
        return self.model.generate_content(prompt).text

    def reason(self, error_log):
        print(f" [synapse] Analyzing error: {error_log[:50]}...")
        
        # Step 1: Retrieval
        context = self.memory.recall(error_log, n_results=1)
        if not context:
            context = "No relevant documentation found."
        else:
            print(" [synapse] Relevant Knowledge Retrieved.")

        # Step 2: Augmentation
        prompt = f"""
        ACT AS A KUBERNETES SITE RELIABILITY ENGINEER (SRE).
        
        Context from Knowledge Base:
        {context}
        
        Real-time Error Log:
        {error_log}
        
        TASK:
        1. Explain the root cause in one sentence.
        2. Suggest the exact `kubectl` command to fix it.
        """
        
        # Step 3: Generation
        print(" [synapse] Thinking...")
        try:
            return self._ask_gemini(prompt)
        except Exception as e:
            return f"Thinking Failed after retries: {e}"

if __name__ == "__main__":
    bot = Synapse()
    test_error = "Pod status is CrashLoopBackOff. Exit Code 137. OOMKilled."
    print("\n=== KubeWhisperer Diagnosis ===")
    print(bot.reason(test_error))