from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class ModelUseClassification(str, Enum):
    RULE_ONLY = "rule_only"
    SMALL_MODEL_ALLOWED = "small_model_allowed"
    LARGE_MODEL_REQUIRED = "large_model_required"
    REQUIRES_CONFIRMATION = "requires_confirmation"


@dataclass(frozen=True)
class ModelUseDecision:
    classification: ModelUseClassification
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "classification": self.classification.value,
            "reason": self.reason,
        }


RULE_ONLY_OPERATIONS = {
    "format_log",
    "format_task_state",
    "json_parse",
    "normalize_path",
    "path_normalize",
    "path_validate",
    "simple_hash",
    "simple_verify",
    "state_format",
    "validate_path",
}

SMALL_MODEL_OPERATIONS = {
    "extract",
    "extraction",
    "light_interpretation",
    "repair_malformed_data",
}

LARGE_MODEL_OPERATIONS = {
    "decision",
    "decision_making",
    "multi_step_reasoning",
    "plan",
    "planning",
    "reasoning",
}

CONFIRMATION_OPERATIONS = {
    "approve",
    "execute",
    "external_action",
    "file_write",
    "mutate_task",
    "queue_task",
    "run_task",
    "write_file",
}

INTENT_OR_DECISION_KEYWORDS = {
    "best",
    "choose",
    "clean this data",
    "decide",
    "fix this config",
    "interpret",
    "meaning",
    "preserve intent",
    "repair invalid json",
    "repair malformed",
    "while keeping meaning",
}

PLANNING_KEYWORDS = {
    "break down",
    "design",
    "multi-step",
    "plan",
    "reason",
    "strategy",
}

CONFIRMATION_KEYWORDS = {
    "approve",
    "delete",
    "execute",
    "external",
    "modify file",
    "queue",
    "run task",
    "write",
    "write file",
}


def classify_model_use(request: Any) -> Dict[str, str]:
    """
    Classify first-pass model usage without side effects.

    This policy only returns classification + reason. It does not select a
    concrete model name, call an executor, queue work, approve actions, or
    mutate task state.
    """
    decision = _classify(request)
    return decision.to_dict()


def add_policy_hint(decision: Any, user_input: Any) -> Any:
    """
    Return a decision copy with optional policy_hint metadata.

    The hint is for log, trace, display, and tests only. It must not control
    routing, model selection, tool selection, approval, queueing, or execution.
    If policy classification fails, the original decision copy is returned
    unchanged.
    """
    decision_copy = copy.deepcopy(decision)
    if not isinstance(decision_copy, dict):
        return decision_copy

    try:
        decision_copy["policy_hint"] = classify_model_use(user_input)
    except Exception:
        return copy.deepcopy(decision)

    return decision_copy


def policy_hint_trace_event(decision: Any) -> Dict[str, str]:
    """
    Build a JSON-ready trace/log event for an attached policy_hint.

    The returned event is observational metadata only.
    """
    hint = _extract_policy_hint(decision)
    if not hint:
        return {}

    return {
        "event": "policy_hint_attached",
        "classification": str(hint.get("classification") or ""),
        "reason": str(hint.get("reason") or ""),
    }


def format_policy_hint_display(decision: Any) -> str:
    """
    Format policy_hint for CLI/UI display without affecting control flow.
    """
    hint = _extract_policy_hint(decision)
    if not hint:
        return ""

    classification = str(hint.get("classification") or "").strip()
    reason = str(hint.get("reason") or "").strip()
    if not classification or not reason:
        return ""

    return f"[policy] {classification} - {reason}"


def _classify(request: Any) -> ModelUseDecision:
    operation = _extract_operation(request)
    text = _extract_text(request)

    if not operation and not text:
        return ModelUseDecision(
            ModelUseClassification.REQUIRES_CONFIRMATION,
            "fail_closed_empty_or_unclassifiable_request",
        )

    if operation in CONFIRMATION_OPERATIONS or _contains_any(text, CONFIRMATION_KEYWORDS):
        return ModelUseDecision(
            ModelUseClassification.REQUIRES_CONFIRMATION,
            "risk_requires_confirmation",
        )

    if operation in LARGE_MODEL_OPERATIONS or _contains_any(text, PLANNING_KEYWORDS):
        return ModelUseDecision(
            ModelUseClassification.LARGE_MODEL_REQUIRED,
            "planning_or_reasoning_requires_large_model",
        )

    if operation in SMALL_MODEL_OPERATIONS:
        return ModelUseDecision(
            ModelUseClassification.SMALL_MODEL_ALLOWED,
            "light_interpretation_or_extraction_allows_small_model",
        )

    if _contains_any(text, INTENT_OR_DECISION_KEYWORDS):
        return ModelUseDecision(
            ModelUseClassification.SMALL_MODEL_ALLOWED,
            "intent_preservation_or_decision_signal_not_rule_only",
        )

    if operation in RULE_ONLY_OPERATIONS:
        return ModelUseDecision(
            ModelUseClassification.RULE_ONLY,
            "allowlisted_deterministic_operation",
        )

    return ModelUseDecision(
        ModelUseClassification.REQUIRES_CONFIRMATION,
        "fail_closed_uncertain_request",
    )


def _extract_operation(request: Any) -> str:
    if isinstance(request, dict):
        for key in ("operation", "intent", "action", "type"):
            value = request.get(key)
            if value:
                return _normalize_token(value)
        return ""
    return ""


def _extract_text(request: Any) -> str:
    if isinstance(request, str):
        return request.strip().lower()

    if isinstance(request, dict):
        values = []
        for key in ("text", "input", "user_input", "description", "prompt"):
            value = request.get(key)
            if isinstance(value, str):
                values.append(value)
        return " ".join(values).strip().lower()

    return str(request or "").strip().lower()


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _contains_any(text: str, needles: set[str]) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return any(needle in normalized for needle in needles)


def _extract_policy_hint(decision: Any) -> Dict[str, Any]:
    if not isinstance(decision, dict):
        return {}

    hint = decision.get("policy_hint")
    if not isinstance(hint, dict):
        return {}

    classification = hint.get("classification")
    reason = hint.get("reason")
    if not classification or not reason:
        return {}

    return hint
