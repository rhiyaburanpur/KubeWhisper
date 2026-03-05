from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from src.brain.synapse import Synapse
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()
# --- Auth Setup ---
API_KEY = os.getenv("KUBEWHISPERER_API_KEY")
if not API_KEY:
    raise RuntimeError("CRITICAL: KUBEWHISPERER_API_KEY environment variable not set.")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key

# --- App & Brain ---
class CrashReport(BaseModel):
    pod_name: str
    error_log: str

app = FastAPI(title="KubeWhisperer Neural Engine")
print(" [server] Loading Synapse Model...")
brain = Synapse()

@app.get("/")
def health_check():
    return {"status": "neural_link_active"}

@app.post("/analyze")
def analyze_crash(report: CrashReport, api_key: str = Security(verify_api_key)):
    """
    Receives logs from Go-Agent -> Returns Diagnosis.
    Requires X-API-Key header.
    """
    print(f" [server] Received crash report for: {report.pod_name}")

    if not report.error_log:
        raise HTTPException(status_code=400, detail="No logs provided")

    diagnosis = brain.reason(report.error_log)
    return {"pod": report.pod_name, "diagnosis": diagnosis}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)