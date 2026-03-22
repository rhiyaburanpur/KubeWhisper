import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MTTRRecord:
    trace_id: str
    scenario_id: str
    pod_name: str
    t1_monitor_ms: float
    t2_analyze_ms: float
    t3_plan_ms: float
    t4_execute_ms: float
    mttr_ms: float
    rag_hit: bool
    success: bool


def now_ms() -> float:
    return time.time() * 1000


def write_mttr_record(record: MTTRRecord, log_path: str = "mttr_log.jsonl") -> None:
    log_path = os.getenv("MTTR_LOG_PATH", log_path)
    with open(log_path, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")