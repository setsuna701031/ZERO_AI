from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


DECISIONS = {
    "applied",
    "ignored_unsupported",
    "ignored_scope_expansion",
    "ignored_policy_conflict",
    "ignored_low_confidence",
    "ignored_duplicate",
    "ignored_irrelevant",
    "ignored_unsafe",
}

SUPPORTED_RECOMMENDATIONS = {
    "create_then_verify",
    "verify_file_exists",
    "verify_target_exists",
    "verify_content_hash",
    "verify_expected_text",
    "verify_directory_exists",
    "read_after_write",
    "create_before_verify",
    "inspect_before_mutation",
    "validate_after_transaction",
    "validate_workspace_relative_path",
    "workspace_contained_write",
    "use_workspace_relative_paths",
    "inspect_failure_evidence_before_retry",
    "content_verification_recommended",
}

UNSAFE_TOKENS = {
    "auto_approve", "skip_validation", "skip_policy", "memory_authority",
    "force_recommendation", "raw_shell", "self_modify", "policy_override",
    "approval_override", "execute_command", "shell_command",
}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _name(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("recommendation") or value.get("pattern") or value.get("name")
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def filter_planning_recommendations(
    recommendations: Any,
    *,
    source_experience_id: str | None = None,
    current_operations: list[str] | None = None,
    current_targets: list[str] | None = None,
    confidence: float = 1.0,
    minimum_confidence: float = 0.25,
    safety_constraints: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Classify memory advice without granting it authority.

    The filter only recognizes declarative planning patterns. It never accepts
    commands, approval changes, new mutation targets, or policy overrides.
    """
    if isinstance(recommendations, (str, Mapping)):
        source = [recommendations]
    else:
        source = list(recommendations or [])
    operations = {str(item).casefold() for item in current_operations or []}
    targets = {str(item).replace("\\", "/").casefold() for item in current_targets or []}
    constraints = {str(item).casefold() for item in safety_constraints or []}
    seen: set[str] = set()
    applied: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for raw in source:
        data = _mapping(raw)
        recommendation = _name(raw)
        source_id = str(data.get("source_experience_id") or source_experience_id or "") or None
        item_confidence = float(data.get("confidence", confidence) or 0.0)
        decision, reason = "applied", "supported_relevant_planning_advice"
        raw_text = str(raw).casefold()
        proposed_target = str(data.get("target") or data.get("path") or "").replace("\\", "/").casefold()
        if not recommendation:
            decision, reason = "ignored_irrelevant", "empty_recommendation"
        elif recommendation in seen:
            decision, reason = "ignored_duplicate", "duplicate_recommendation"
        elif any(token in recommendation or token in raw_text for token in UNSAFE_TOKENS):
            decision, reason = "ignored_unsafe", "recommendation_could_change_execution_authority"
        elif any(key in data for key in ("command", "commands", "shell", "argv", "callable")):
            decision, reason = "ignored_unsafe", "executable_recommendation_forbidden"
        elif proposed_target and proposed_target not in targets:
            decision, reason = "ignored_scope_expansion", "recommendation_introduces_new_target"
        elif data.get("operation") and str(data["operation"]).casefold() not in operations:
            decision, reason = "ignored_scope_expansion", "recommendation_introduces_new_operation"
        elif data.get("requires_approval_bypass") or data.get("policy_override"):
            decision, reason = "ignored_policy_conflict", "approval_and_policy_constraints_are_immutable"
        elif item_confidence < minimum_confidence:
            decision, reason = "ignored_low_confidence", "recommendation_confidence_below_threshold"
        elif recommendation not in SUPPORTED_RECOMMENDATIONS:
            decision, reason = "ignored_unsupported", "planner_capability_not_allowlisted"
        elif recommendation in {"create_then_verify", "verify_file_exists", "verify_target_exists", "verify_content_hash", "verify_expected_text", "read_after_write", "content_verification_recommended"} and "create_file" not in operations:
            decision, reason = "ignored_irrelevant", "file_creation_pattern_not_relevant"
        elif recommendation == "verify_directory_exists" and "create_directory" not in operations:
            decision, reason = "ignored_irrelevant", "directory_creation_pattern_not_relevant"
        elif recommendation == "inspect_before_mutation" and not operations.intersection({"create_file", "create_directory"}):
            decision, reason = "ignored_irrelevant", "no_mutation_to_precede"
        elif "operator_approval" not in constraints and data.get("requires_approval_change"):
            decision, reason = "ignored_policy_conflict", "approval_constraint_cannot_be_added_or_removed_by_memory"
        record = {
            "recommendation": recommendation,
            "source_experience_id": source_id,
            "decision": decision,
            "reason": reason,
        }
        (applied if decision == "applied" else ignored).append(record)
        seen.add(recommendation)
    return {"applied": applied, "ignored": ignored}


filter_recommendations = filter_planning_recommendations

__all__ = ["DECISIONS", "SUPPORTED_RECOMMENDATIONS", "filter_planning_recommendations", "filter_recommendations"]
