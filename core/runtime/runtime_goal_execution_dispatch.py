from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_goal_executor import (
    REQUEST_CONTRACT as GOAL_EXECUTION_REQUEST_CONTRACT,
    create_goal_execution_request,
)
from core.runtime.runtime_operator_session import fingerprint, time_text

CONTRACT = "zero.runtime.goal_execution_dispatch.v1"
DISPATCHABLE_SESSION_STATUS = "waiting_for_candidate_bundle"
SUPPORTED_GOAL_TYPES = {"inspect", "document", "modify", "validate"}
FORBIDDEN_CONTEXT_FIELDS = {
    "argv",
    "callable",
    "command",
    "dynamic_import",
    "eval",
    "exec",
    "network",
    "shell",
    "subprocess",
}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip().replace("\\", "/")
        if text and text not in result:
            result.append(text)
    return result


def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value)
    result.pop("dispatch_fingerprint", None)
    return result


def seal_goal_execution_dispatch(
    dispatch: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(dispatch)
    value["dispatch_fingerprint"] = fingerprint(value)
    return value


def _normalized_goal_from_session(
    session: Mapping[str, Any],
) -> dict[str, Any]:
    natural = _mapping(session.get("natural_task"))

    goal_id = str(
        natural.get("goal_id")
        or session.get("goal_id")
        or ""
    ).strip()
    mission_id = str(
        natural.get("mission_id")
        or session.get("mission_id")
        or ""
    ).strip()
    goal_type = str(
        natural.get("goal_type")
        or ""
    ).strip().lower()

    target_scope = _string_list(
        natural.get("approved_target_scope")
        or natural.get("target_files")
        or []
    )
    excluded_scope = _string_list(
        natural.get("excluded_scope")
        or []
    )

    goal = {
        "goal_id": goal_id,
        "mission_id": mission_id,
        "goal_type": goal_type,
        "goal_title": str(
            natural.get("goal_title")
            or ""
        ).strip(),
        "goal_description": str(
            natural.get("goal_description")
            or natural.get("text")
            or natural.get("task")
            or ""
        ).strip(),
        "target_scope": target_scope,
        "excluded_scope": excluded_scope,
        "acceptance_criteria": deepcopy(
            natural.get("acceptance_criteria")
            or []
        ),
        "validation_requirements": deepcopy(
            natural.get("validation_requirements")
            or []
        ),
        "operator_confirmation_required": bool(
            natural.get("operator_confirmation_required", True)
        ),
        "authoring_instruction": _mapping(
            natural.get("authoring_instruction")
        ),
        "goal_fingerprint": natural.get("goal_fingerprint"),
    }

    if not goal["goal_fingerprint"]:
        goal["goal_fingerprint"] = fingerprint(
            {
                key: deepcopy(value)
                for key, value in goal.items()
                if key != "goal_fingerprint"
            }
        )

    return goal


def _operator_context_from_session(
    session: Mapping[str, Any],
    goal: Mapping[str, Any],
) -> dict[str, Any]:
    natural = _mapping(session.get("natural_task"))
    session_context = _mapping(session.get("operator_context"))
    natural_context = _mapping(natural.get("operator_context"))
    instruction = (
        _mapping(goal.get("authoring_instruction"))
        or _mapping(natural.get("authoring_instruction"))
    )

    context: dict[str, Any] = {}

    for source in (session_context, natural_context):
        for key, value in source.items():
            if key not in context:
                context[key] = deepcopy(value)

    if instruction:
        context["authoring_instruction"] = instruction

    for key in (
        "append_text",
        "exact_text",
        "replacement_text",
        "expected_text",
        "authoring_strategy",
        "template_name",
        "template_fields",
        "import_statement",
        "create_content",
    ):
        if key in natural and key not in context:
            context[key] = deepcopy(natural[key])

    return context


def validate_goal_execution_dispatch(
    dispatch: Mapping[str, Any],
) -> list[str]:
    value = _mapping(dispatch)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append("invalid_goal_execution_dispatch_contract")

    if value.get("dispatch_fingerprint") != fingerprint(
        _unsigned(value)
    ):
        reasons.append("goal_execution_dispatch_fingerprint_mismatch")

    if not str(value.get("dispatch_id") or "").strip():
        reasons.append("dispatch_id_required")

    if not str(value.get("session_id") or "").strip():
        reasons.append("session_id_required")

    if not str(value.get("goal_id") or "").strip():
        reasons.append("goal_id_required")

    if not str(value.get("mission_id") or "").strip():
        reasons.append("mission_id_required")

    if value.get("session_status") != DISPATCHABLE_SESSION_STATUS:
        reasons.append("session_not_waiting_for_candidate_bundle")

    request = _mapping(value.get("execution_request"))
    if request.get("contract") != GOAL_EXECUTION_REQUEST_CONTRACT:
        reasons.append("invalid_embedded_goal_execution_request")

    if request.get("session_id") != value.get("session_id"):
        reasons.append("dispatch_request_session_mismatch")

    if request.get("goal_id") != value.get("goal_id"):
        reasons.append("dispatch_request_goal_mismatch")

    if request.get("mission_id") != value.get("mission_id"):
        reasons.append("dispatch_request_mission_mismatch")

    if request.get("execution_request_fingerprint") != value.get(
        "execution_request_fingerprint"
    ):
        reasons.append("dispatch_request_fingerprint_mismatch")

    if value.get("workspace_mutated") is not False:
        reasons.append("dispatch_must_not_mutate_workspace")

    if value.get("transaction_invoked") is not False:
        reasons.append("dispatch_must_not_invoke_transaction")

    if value.get("operator_input_submitted") is not False:
        reasons.append("dispatch_must_not_submit_operator_input")

    return sorted(set(reasons))


def build_goal_execution_dispatch(
    session: Mapping[str, Any],
    *,
    artifact_root: Any,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(session)
    reasons: list[str] = []

    if value.get("session_status") != DISPATCHABLE_SESSION_STATUS:
        reasons.append("session_not_waiting_for_candidate_bundle")

    if value.get("required_action") != "candidate_bundle":
        reasons.append("candidate_bundle_action_not_required")

    if value.get("required_input_contract") is None:
        reasons.append("candidate_bundle_contract_required")

    session_id = str(value.get("session_id") or "").strip()
    if not session_id:
        reasons.append("session_id_required")

    session_fingerprint = value.get("session_fingerprint")
    if not str(session_fingerprint or "").strip():
        reasons.append("session_fingerprint_required")

    goal = _normalized_goal_from_session(value)

    if not goal.get("goal_id"):
        reasons.append("goal_id_required")

    if not goal.get("mission_id"):
        reasons.append("mission_id_required")

    if goal.get("goal_type") not in SUPPORTED_GOAL_TYPES:
        reasons.append("unsupported_or_missing_goal_type")

    if not goal.get("target_scope"):
        reasons.append("approved_scope_required")

    if set(goal.get("target_scope") or []) & set(
        goal.get("excluded_scope") or []
    ):
        reasons.append("approved_scope_intersects_excluded_scope")

    operator_context = _operator_context_from_session(value, goal)
    if FORBIDDEN_CONTEXT_FIELDS & set(operator_context):
        reasons.append("executable_operator_context_forbidden")

    if goal.get("goal_type") in {"modify", "document"}:
        instruction = _mapping(
            operator_context.get("authoring_instruction")
        )
        has_legacy_instruction = any(
            key in operator_context
            for key in (
                "append_text",
                "exact_text",
                "replacement_text",
            )
        )
        if not instruction and not has_legacy_instruction:
            reasons.append("authoring_instruction_required")

    artifact_root_text = str(artifact_root or "").strip()
    if not artifact_root_text:
        reasons.append("artifact_root_required")

    if reasons:
        raise ValueError(";".join(sorted(set(reasons))))

    request = create_goal_execution_request(
        goal,
        value,
        operator_context=operator_context,
        now=now,
    )

    identity = {
        "session_id": session_id,
        "session_fingerprint": session_fingerprint,
        "goal_id": goal["goal_id"],
        "goal_fingerprint": goal["goal_fingerprint"],
        "execution_request_fingerprint": request[
            "execution_request_fingerprint"
        ],
        "artifact_root": artifact_root_text,
    }

    dispatch = seal_goal_execution_dispatch(
        {
            "contract": CONTRACT,
            "dispatch_id": (
                f"goal-dispatch-{fingerprint(identity)[:20]}"
            ),
            "dispatch_status": "ready",
            "created_at": time_text(now),
            "session_id": session_id,
            "session_fingerprint": session_fingerprint,
            "session_status": value.get("session_status"),
            "mission_id": goal["mission_id"],
            "goal_id": goal["goal_id"],
            "goal_type": goal["goal_type"],
            "goal_fingerprint": goal["goal_fingerprint"],
            "approved_scope": deepcopy(
                goal.get("target_scope") or []
            ),
            "excluded_scope": deepcopy(
                goal.get("excluded_scope") or []
            ),
            "artifact_root": artifact_root_text,
            "execution_request": request,
            "execution_request_fingerprint": request[
                "execution_request_fingerprint"
            ],
            "workspace_mutated": False,
            "transaction_invoked": False,
            "operator_input_submitted": False,
            "approval_performed": False,
            "review_performed": False,
            "authorization_performed": False,
            "audit_record": {
                "event_type": (
                    "runtime_goal_execution_dispatch_created"
                ),
                "created_at": time_text(now),
                "session_id": session_id,
                "goal_id": goal["goal_id"],
            },
        }
    )

    validation_reasons = validate_goal_execution_dispatch(dispatch)
    if validation_reasons:
        raise ValueError(";".join(validation_reasons))

    return dispatch


__all__ = [
    "CONTRACT",
    "DISPATCHABLE_SESSION_STATUS",
    "SUPPORTED_GOAL_TYPES",
    "build_goal_execution_dispatch",
    "seal_goal_execution_dispatch",
    "validate_goal_execution_dispatch",
]
