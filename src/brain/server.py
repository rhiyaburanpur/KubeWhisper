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
from typing import Optional

from src.brain.metrics import (
    DIAGNOSIS_REQUESTS_TOTAL,
    DIAGNOSIS_DURATION_SECONDS,
    RAG_CONTEXT_HITS_TOTAL,
)
from src.brain.mttr import MTTRRecord, now_ms, write_mttr_record
from src.brain.synapse import Synapse
from src.brain.validator import validate_response
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("KUBEWHISPER.brain")


def log(level: str, msg: str, **kwargs):
    record = {"level": level, "service": "brain", "msg": msg}
    record.update(kwargs)
    logger.info(json.dumps(record))


API_KEY = os.getenv("KUBEWHISPER_API_KEY")
if not API_KEY:
    raise RuntimeError("CRITICAL: KUBEWHISPER_API_KEY environment variable not set.")

HALLUCINATION_LOG_PATH = os.getenv("HALLUCINATION_LOG_PATH", "hallucination_log.jsonl")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key


class CrashReport(BaseModel):
    pod_name: str
    error_log: str
    scenario_id: Optional[str] = "unknown"
    t1_monitor_ms: Optional[float] = None
    t2_analyze_ms: Optional[float] = None
    ablation_mode: bool = False


app = FastAPI(title="KUBEWHISPER Neural Engine")

log("info", "Loading Synapse model...")
brain = Synapse()
log("info", "Brain online.")


def write_hallucination_record(
    trace_id: str,
    pod_name: str,
    scenario_id: str,
    failure_reason: str,
    raw_llm_output: str,
) -> None:
    record = {
        "trace_id": trace_id,
        "pod_name": pod_name,
        "scenario_id": scenario_id,
        "failure_reason": failure_reason,
        "raw_llm_output": raw_llm_output,
        "timestamp_ms": now_ms(),
    }
    with open(HALLUCINATION_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


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
    t3_plan_ms = now_ms()

    log("info", "Crash report received",
        trace_id=trace_id,
        pod=report.pod_name,
        scenario_id=report.scenario_id,
        t1_monitor_ms=report.t1_monitor_ms,
        t2_analyze_ms=report.t2_analyze_ms,
        ablation_mode=report.ablation_mode,
    )

    if not report.error_log:
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="error").inc()
        raise HTTPException(status_code=400, detail="No logs provided")

    try:
        diagnosis, rag_hit, parsed_schema = brain.reason(
            report.error_log,
            use_rag=not report.ablation_mode,
        )
        t4_execute_ms = now_ms()

        duration_s = (t4_execute_ms - t3_plan_ms) / 1000
        DIAGNOSIS_DURATION_SECONDS.observe(duration_s)
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="success").inc()
        RAG_CONTEXT_HITS_TOTAL.labels(hit=str(rag_hit).lower()).inc()

        validation_passed = False
        failure_reason = None

        if parsed_schema is None:
            failure_reason = "parse_failure: could not extract structured JSON from LLM output"
            write_hallucination_record(
                trace_id=trace_id,
                pod_name=report.pod_name,
                scenario_id=report.scenario_id,
                failure_reason=failure_reason,
                raw_llm_output=diagnosis,
            )
            log("warn", "Schema parse failure",
                trace_id=trace_id,
                pod=report.pod_name,
                failure_reason=failure_reason,
            )
        else:
            allowlist_failure = validate_response(parsed_schema)
            if allowlist_failure:
                failure_reason = allowlist_failure
                write_hallucination_record(
                    trace_id=trace_id,
                    pod_name=report.pod_name,
                    scenario_id=report.scenario_id,
                    failure_reason=failure_reason,
                    raw_llm_output=diagnosis,
                )
                log("warn", "Command allowlist violation",
                    trace_id=trace_id,
                    pod=report.pod_name,
                    failure_reason=failure_reason,
                )
            else:
                validation_passed = True

        mttr_ms = None
        if report.t1_monitor_ms is not None:
            mttr_ms = t4_execute_ms - report.t1_monitor_ms

        mttr_record = MTTRRecord(
            trace_id=trace_id,
            scenario_id=report.scenario_id,
            pod_name=report.pod_name,
            t1_monitor_ms=report.t1_monitor_ms or 0.0,
            t2_analyze_ms=report.t2_analyze_ms or 0.0,
            t3_plan_ms=t3_plan_ms,
            t4_execute_ms=t4_execute_ms,
            mttr_ms=mttr_ms or (t4_execute_ms - t3_plan_ms),
            rag_hit=rag_hit,
            success=True,
        )
        write_mttr_record(mttr_record)

        log("info", "Diagnosis complete",
            trace_id=trace_id,
            pod=report.pod_name,
            scenario_id=report.scenario_id,
            duration_seconds=round(duration_s, 3),
            mttr_ms=round(mttr_ms, 2) if mttr_ms else None,
            rag_hit=rag_hit,
            validation_passed=validation_passed,
            ablation_mode=report.ablation_mode,
        )

        return {
            "pod": report.pod_name,
            "diagnosis": diagnosis,
            "trace_id": trace_id,
            "scenario_id": report.scenario_id,
            "validation_passed": validation_passed,
            "failure_reason": failure_reason,
            "timestamps": {
                "t1_monitor_ms": report.t1_monitor_ms,
                "t2_analyze_ms": report.t2_analyze_ms,
                "t3_plan_ms": t3_plan_ms,
                "t4_execute_ms": t4_execute_ms,
                "mttr_ms": mttr_ms,
            }
        }

    except Exception as e:
        DIAGNOSIS_REQUESTS_TOTAL.labels(status="error").inc()
        log("error", "Diagnosis failed",
            trace_id=trace_id,
            pod=report.pod_name,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Diagnosis failed.")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)