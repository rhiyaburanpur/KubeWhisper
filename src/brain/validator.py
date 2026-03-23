import re
from typing import Optional
from pydantic import BaseModel, field_validator


ALLOWED_VERBS = {
    "get", "describe", "logs", "rollout", "set",
    "scale", "apply", "create", "patch", "top"
}

BLOCKED_PATTERNS = ["--force", "--grace-period=0", "delete"]


class DiagnosisSchema(BaseModel):
    root_cause: str
    confidence: float
    remediation_commands: list[str]
    affected_resources: list[str]

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("root_cause")
    @classmethod
    def root_cause_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("root_cause must not be empty")
        return v.strip()

    @field_validator("remediation_commands")
    @classmethod
    def commands_not_empty(cls, v):
        if not v:
            raise ValueError("remediation_commands must contain at least one command")
        return v


def _check_command_allowlist(commands: list[str]) -> Optional[str]:
    for cmd in commands:
        for pattern in BLOCKED_PATTERNS:
            if pattern in cmd:
                return f"blocked_pattern: {pattern}"

        tokens = cmd.strip().split()
        if not tokens:
            continue

        if tokens[0] == "kubectl" and len(tokens) > 1:
            verb = tokens[1]
        else:
            verb = tokens[0]

        if verb not in ALLOWED_VERBS:
            return f"blocked_verb: {verb}"

    return None


def validate_response(parsed: DiagnosisSchema) -> Optional[str]:
    """
    Validates a parsed DiagnosisSchema against the command allowlist.
    Returns None if valid, or a failure reason string if invalid.
    """
    return _check_command_allowlist(parsed.remediation_commands)