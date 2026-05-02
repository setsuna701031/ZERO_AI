from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


HIGH_RISK_TERMS: Tuple[str, ...] = (
    "delete",
    "remove",
    "rm ",
    "rmdir",
    "erase",
    "format",
    "shutdown",
    "reboot",
    "kill",
    "drop table",
    "truncate",
    "credential",
    "credentials",
    "secret",
    "token",
    "password",
    "private key",
)

MEDIUM_RISK_TERMS: Tuple[str, ...] = (
    "overwrite",
    "replace",
    "commit",
    "push",
    "install",
    "download",
    "network",
)


def evaluate_persona_runtime_policy(task_text: str) -> Dict[str, Any]:
    """
    Classify persona runtime task risk before bridge execution.

    This layer is intentionally advisory/gating only. It does not choose tools,
    retry, confirm with the user, mutate scheduler state, or execute anything.
    """
    text = str(task_text or "").strip()
    lowered = f" {text.lower()} "
    matched_high = _matching_terms(lowered, HIGH_RISK_TERMS)
    matched_medium = _matching_terms(lowered, MEDIUM_RISK_TERMS)

    if matched_high:
        risk_level = "high"
        confirmation_required = True
        allowed = False
        blocked_reason = "policy blocked high-risk task before runtime execution"
        policy_action = "block"
        matched_terms = matched_high
    elif matched_medium:
        risk_level = "medium"
        confirmation_required = True
        allowed = True
        blocked_reason = ""
        policy_action = "mark_confirmation_required"
        matched_terms = matched_medium
    else:
        risk_level = "low"
        confirmation_required = False
        allowed = True
        blocked_reason = ""
        policy_action = "allow"
        matched_terms = []

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "persona_runtime_policy_layer",
        "input_summary": _summarize_task(text),
        "risk_level": risk_level,
        "confirmation_required": confirmation_required,
        "allowed": allowed,
        "blocked_reason": blocked_reason,
        "policy_action": policy_action,
        "matched_terms": matched_terms,
        "decision_basis": "static task text risk classification",
        "affects_tool_execution": False,
        "affects_scheduler": False,
        "retry_allowed": False,
    }


def policy_decision_trace(policy_decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(policy_decision, dict) or not policy_decision:
        return []
    return [
        {
            "timestamp": str(policy_decision.get("timestamp") or ""),
            "source": str(policy_decision.get("source") or "persona_runtime_policy_layer"),
            "event_type": "policy_decision",
            "risk_level": str(policy_decision.get("risk_level") or ""),
            "confirmation_required": bool(policy_decision.get("confirmation_required")),
            "allowed": bool(policy_decision.get("allowed", True)),
            "policy_action": str(policy_decision.get("policy_action") or ""),
            "blocked_reason": str(policy_decision.get("blocked_reason") or ""),
            "matched_terms": list(policy_decision.get("matched_terms") or []),
            "decision_basis": str(policy_decision.get("decision_basis") or ""),
            "affects_tool_execution": False,
            "affects_scheduler": False,
        }
    ]


def _matching_terms(lowered_text: str, terms: Tuple[str, ...]) -> List[str]:
    matched: List[str] = []
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized:
            continue
        if normalized in lowered_text:
            matched.append(normalized)
    return matched


def _summarize_task(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= 160:
        return normalized
    return f"{normalized[:157]}..."
