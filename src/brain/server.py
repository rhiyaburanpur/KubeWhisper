import json
import logging
import time
import uuid

from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.responses import Response
from fastapi.security.api_key import APIKeyHeader
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

from src.brain.metrics import (
    DIAGNOSIS_REQUESTS_TOTAL,
    DIAGNOSIS_DURATION_SECONDS,
    RAG_CONTEXT_HITS_TOTAL,
)
from src.brain.synapse import Synapse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("kubewhisperer.brain")


def log(level: str, msg: str, **kwargs):
    record = {"level": level, "service": "brain", "msg": msg}
    record.update(kwargs)
    logger.info(json.dumps(record))


API_KEY = os.getenv("KUBEWHISPERER_API_KEY")
if not API_KEY:
    raise RuntimeError("CRITICAL: KUBEWHISPERER_API_KEY environment variable not set.")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key


class CrashReport(BaseModel):
    pod_name: str
    error_log: str


app = FastAPI(title="KubeWhisperer Neural Engine")

log("info", "Loading Synapse model...")
brain = Synapse()
log("info", "Brain online.")


@app.get("/")
def health_check():
    return {"status": "neural_link_active"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze")
def analyze_crash(
    request: Request,
    report: CrashReport,
    api_key: str = Security(verify_api_key),
):
    trace_id = str(uuid.uuid4())[:8]
    start = time.monotonic()

    log("info", "Crash report received", trace_id=trace_id, pod=report.pod_name)

    if not report.error_log:
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="error").inc()
        raise HTTPException(status_code=400, detail="No logs provided")

    try:
        diagnosis, rag_hit = brain.reason(report.error_log)

        duration = time.monotonic() - start
        DIAGNOSIS_DURATION_SECONDS.observe(duration)
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="success").inc()
        RAG_CONTEXT_HITS_TOTAL.labels(hit=str(rag_hit).lower()).inc()

        log(
            "info",
            "Diagnosis complete",
            trace_id=trace_id,
            pod=report.pod_name,
            duration_seconds=round(duration, 3),
            rag_hit=rag_hit,
        )

        return {"pod": report.pod_name, "diagnosis": diagnosis, "trace_id": trace_id}

    except Exception as e:
        duration = time.monotonic() - start
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="error").inc()
        log("error", "Diagnosis failed", trace_id=trace_id, pod=report.pod_name, error=str(e))
        raise HTTPException(status_code=500, detail="Diagnosis failed.")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)