from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, time_text
from core.runtime.runtime_planning_recommendation_filter import filter_planning_recommendations


CONTRACT = "zero.runtime.agent_planning_feedback.v1"
PLANNER_VERSION = "memory-guided-deterministic-v1"
MAX_EXPERIENCES = 3
MAX_ITEMS = 16
SENSITIVE_KEY = re.compile(r"(?:secret|token|password|credential|api[_-]?key|authorization|cookie)", re.I)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _bounded_strings(values: Any, limit: int = MAX_ITEMS) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result and not SENSITIVE_KEY.search(text):
            result.append(text[:240])
        if len(result) >= limit:
            break
    return result


def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value)
    result.pop("feedback_fingerprint", None)
    return result


def seal_planning_feedback(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned(value)
    result["feedback_fingerprint"] = fingerprint(result)
    return result


def validate_planning_feedback(value: Mapping[str, Any]) -> list[str]:
    item = _mapping(value)
    reasons: list[str] = []
    if item.get("contract") != CONTRACT:
        reasons.append("invalid_planning_feedback_contract")
    if item.get("feedback_fingerprint") != fingerprint(_unsigned(item)):
        reasons.append("planning_feedback_fingerprint_mismatch")
    for key in ("feedback_id", "query_text", "mission_input_fingerprint", "memory_context_fingerprint", "created_at", "idempotency_key"):
        if not str(item.get(key) or "").strip():
            reasons.append(f"{key}_required")
    for key in ("experience_references", "matched_tokens", "successful_patterns", "failure_patterns", "recommended_goal_patterns", "recommended_validations", "recommended_evidence", "recommended_ordering", "risk_notes", "avoid_patterns", "ignored_recommendations", "applied_recommendations"):
        if not isinstance(item.get(key), list):
            reasons.append(f"{key}_required")
    if len(item.get("experience_references") or []) > MAX_EXPERIENCES:
        reasons.append("planning_feedback_experience_limit_exceeded")
    if any(key in item for key in ("command", "commands", "shell", "argv", "execution_authority")):
        reasons.append("planning_feedback_authority_forbidden")
    return sorted(set(reasons))


def _valid_memory_context(context: Mapping[str, Any]) -> bool:
    item = _mapping(context)
    claimed = item.pop("context_fingerprint", None)
    return bool(claimed) and claimed == fingerprint(item)


def build_agent_planning_feedback(
    query_text: str,
    *,
    structured_intents: list[Mapping[str, Any]] | None = None,
    memory_context: Mapping[str, Any] | None = None,
    workspace_root: Any = None,
    target_root: Any = None,
    safety_constraints: list[str] | None = None,
    planner_version: str = PLANNER_VERSION,
    now: Any = None,
) -> dict[str, Any]:
    text = str(query_text or "").strip()
    if not text:
        raise ValueError("planning_feedback_query_required")
    intents = [_mapping(item) for item in structured_intents or []]
    operations = [str(item.get("operation") or "") for item in intents]
    targets = [str(item.get("path") or "") for item in intents if item.get("path")]
    raw_context = _mapping(memory_context)
    valid_context = _valid_memory_context(raw_context) if raw_context else False
    context = raw_context if valid_context else {}
    references = []
    for reference in context.get("experience_references") or []:
        item = _mapping(reference)
        references.append({key: item.get(key) for key in ("experience_id", "similarity_score", "outcome")})
        if len(references) >= MAX_EXPERIENCES:
            break
    successful = _bounded_strings(context.get("successful_patterns"))
    failures = _bounded_strings(context.get("failure_patterns"))
    validations = _bounded_strings(context.get("recommended_validations"))
    recommendations: list[Any] = []
    recommendations.extend(successful)
    recommendations.extend(validations)
    recommendations.extend(context.get("recommended_ordering") or [])
    recommendations.extend(raw for raw in (context.get("recommendations") or []) if not SENSITIVE_KEY.search(str(raw)))
    source_id = references[0].get("experience_id") if references else None
    filtered = filter_planning_recommendations(
        recommendations,
        source_experience_id=source_id,
        current_operations=operations,
        current_targets=targets,
        confidence=max((float(item.get("similarity_score") or 0.0) for item in references), default=1.0 if not references else 0.0),
        safety_constraints=safety_constraints,
    )
    applied_names = [item["recommendation"] for item in filtered["applied"]]
    goal_patterns = [name for name in applied_names if name in {"create_then_verify", "inspect_before_mutation"}]
    recommended_validations = [name for name in applied_names if name.startswith("verify_") or name in {"read_after_write", "validate_workspace_relative_path"}]
    if "create_then_verify" in applied_names and "verify_file_exists" not in recommended_validations:
        recommended_validations.append("verify_file_exists")
    evidence = []
    if any(name in recommended_validations for name in ("verify_file_exists", "verify_target_exists", "verify_directory_exists")):
        evidence.append("path_existence_evidence")
    if "verify_content_hash" in recommended_validations:
        evidence.append("content_hash_evidence")
    if "read_after_write" in recommended_validations or "verify_expected_text" in recommended_validations:
        evidence.append("read_only_preview_evidence")
    ordering = [name for name in applied_names if name in {"create_before_verify", "inspect_before_mutation", "validate_after_transaction"}]
    if "create_then_verify" in applied_names and "create_before_verify" not in ordering:
        ordering.append("create_before_verify")
    risks = _bounded_strings(context.get("risk_notes"))
    if not valid_context and raw_context:
        risks.append("memory_feedback_invalid")
    avoid = failures
    if "path_traversal" in failures and "workspace_containment_required" not in risks:
        risks.append("workspace_containment_required")
    mission_seed = {"query_text": text, "structured_intents": intents, "workspace_root": str(workspace_root or ""), "target_root": str(target_root or "")}
    memory_fingerprint = str(raw_context.get("context_fingerprint") or fingerprint({"memory_context": "unavailable"}))
    idempotency_key = fingerprint({"mission": mission_seed, "memory_context_fingerprint": memory_fingerprint, "planner_version": planner_version})
    feedback_id = f"planning-feedback-{idempotency_key[:20]}"
    confidence = round(max((float(item.get("similarity_score") or 0.0) for item in references), default=0.0), 6)
    value = {
        "contract": CONTRACT,
        "feedback_id": feedback_id,
        "query_text": text,
        "mission_input_fingerprint": fingerprint(mission_seed),
        "memory_context_fingerprint": memory_fingerprint,
        "experience_references": references,
        "matched_tokens": _bounded_strings(context.get("matched_tokens"), 40),
        "successful_patterns": successful,
        "failure_patterns": failures,
        "recommended_goal_patterns": goal_patterns,
        "recommended_validations": sorted(set(recommended_validations)),
        "recommended_evidence": sorted(set(evidence)),
        "recommended_ordering": ordering,
        "risk_notes": _bounded_strings(risks),
        "avoid_patterns": avoid,
        "ignored_recommendations": filtered["ignored"],
        "applied_recommendations": filtered["applied"],
        "confidence": confidence,
        "created_at": time_text(now),
        "idempotency_key": idempotency_key,
        "planner_version": planner_version,
    }
    return seal_planning_feedback(value)


def save_planning_feedback(value: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sealed = seal_planning_feedback(value)
    reasons = validate_planning_feedback(sealed)
    if reasons:
        raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return sealed


def load_planning_feedback(path: Any) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_planning_feedback_json") from exc
    reasons = validate_planning_feedback(value)
    if reasons:
        raise ValueError(";".join(reasons))
    return value


build_planning_feedback = build_agent_planning_feedback

__all__ = ["CONTRACT", "PLANNER_VERSION", "build_agent_planning_feedback", "build_planning_feedback", "load_planning_feedback", "save_planning_feedback", "seal_planning_feedback", "validate_planning_feedback"]
