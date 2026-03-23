# Phase 9 — Schema Validation and Hallucination Rate Measurement

## Objective

Enforce structured output on all Gemini responses and measure the hallucination rate.
This produces the auditable evidence required by the paper's `<2% hallucination rate` claim.

## New Files

- `src/brain/validator.py` — Pydantic DiagnosisSchema + command allowlist checker
- `hallucination_log.jsonl` — runtime output, one record per failed validation (gitignored)

## Modified Files

- `src/brain/synapse.py` — updated prompt format (JSON output), added `_parse_structured_response()`, `reason()` now returns a 3-tuple
- `src/brain/server.py` — unpacks 3-tuple, runs `validate_response()`, writes hallucination records, adds `validation_passed` and `failure_reason` to the API response

## Schema

```python
class DiagnosisSchema(BaseModel):
    root_cause: str
    confidence: float       # 0.0 to 1.0
    remediation_commands: list[str]
    affected_resources: list[str]
```

## Command Allowlist

Allowed verbs: `get`, `describe`, `logs`, `rollout`, `set`, `scale`, `apply`, `create`, `patch`, `top`

Blocked patterns: `--force`, `--grace-period=0`, `delete`

## Validation Logic

Two failure modes are tracked:

1. `parse_failure` — Gemini response could not be parsed into the schema (malformed JSON, missing fields, confidence out of range)
2. `blocked_verb` / `blocked_pattern` — a remediation command uses a disallowed kubectl verb or flag

On either failure: raw LLM text is returned to the Go agent (operator can still read it), `validation_passed: false` is included in the response, and a record is written to `hallucination_log.jsonl`.

## Hallucination Rate Formula

```
hallucination_rate = failed_validations / total_responses
```

Both values are derivable from `hallucination_log.jsonl` (count of records) and `mttr_log.jsonl` (count of records with `success: true`).

## hallucination_log.jsonl Record Format

```json
{
  "trace_id": "abc123",
  "pod_name": "scenario-01-oom-heap",
  "scenario_id": "01",
  "failure_reason": "blocked_verb: delete",
  "raw_llm_output": "...",
  "timestamp_ms": 1774168539084.1
}
```

## Status

Implementation complete. Verification pending — run scenario-01 and confirm:
1. Brain response includes `validation_passed: true`
2. No record written to `hallucination_log.jsonl` for a clean run