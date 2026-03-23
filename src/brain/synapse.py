import json
import os
import re
from typing import Optional

from google import genai
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from src.brain.memory import KnowledgeBase
from src.brain.validator import DiagnosisSchema


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

    def _parse_structured_response(self, raw: str) -> Optional[DiagnosisSchema]:
        """
        Attempts to parse Gemini's response into a DiagnosisSchema.
        Gemini is prompted to return a JSON block. This method extracts
        and validates that block. Returns None if parsing fails.
        """
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", raw, re.DOTALL)

        if not match:
            print(" [synapse] Could not locate JSON block in Gemini response.")
            return None

        try:
            data = json.loads(match.group(1))
            return DiagnosisSchema(**data)
        except Exception as e:
            print(f" [synapse] Schema parse error: {e}")
            return None

    def reason(self, error_log: str) -> tuple[str, bool, Optional[DiagnosisSchema]]:
        """
        Runs the RAG pipeline.
        Returns (diagnosis_str, rag_hit, parsed_schema).
        parsed_schema is None if Gemini output could not be parsed.
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
Analyze this crash and respond ONLY with a JSON block in the following exact format. Do not include any text before or after the JSON block.

```json
{{
  "root_cause": "<one sentence explaining what caused the crash>",
  "confidence": <float between 0.0 and 1.0 representing your confidence>,
  "remediation_commands": ["<kubectl command 1>", "<kubectl command 2>"],
  "affected_resources": ["<resource/name>"]
}}
```

Use only safe kubectl verbs: get, describe, logs, rollout, set, scale, apply, create, patch, top.
Do not use: delete, --force, --grace-period=0.
"""
        print(" [synapse] Consulting Gemini AI...")
        try:
            raw_response = self._ask_gemini(prompt)
            print(" [synapse] Analysis complete.")
            parsed = self._parse_structured_response(raw_response)
            return raw_response, rag_hit, parsed
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
            return error_msg, rag_hit, None