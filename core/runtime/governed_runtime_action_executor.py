from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "governed_runtime_action_executor.v1"

EXECUTION_READY = "ready"
EXECUTION_DRY_RUN = "dry_run"
EXECUTION_REVIEW_REQUIRED = "review_required"
EXECUTION_BLOCKED = "blocked"
EXECUTION_COMPLETED = "completed"
EXECUTION_FAILED = "failed"

EXECUTION_STATES: tuple[str, ...] = (
    EXECUTION_READY,
    EXECUTION_DRY_RUN,
    EXECUTION_REVIEW_REQUIRED,
    EXECUTION_BLOCKED,
    EXECUTION_COMPLETED,
    EXECUTION_FAILED,
)

ACTION_NO_ACTION = "no_action"
ACTION_DRY_RUN_REPAIR = "dry_run_repair"
ACTION_DRY_RUN_REPLAY = "dry_run_replay"
ACTION_DRY_RUN_PLANNER_HANDOFF = "dry_run_planner_handoff"
ACTION_APPROVAL_REQUIRED_REPAIR = "approval_required_repair"
ACTION_APPROVAL_REQUIRED_REPLAY = "approval_required_replay"
ACTION_BLOCKED = "blocked"

ACTION_TYPES: tuple[str, ...] = (
    ACTION_NO_ACTION,
    ACTION_DRY_RUN_REPAIR,
    ACTION_DRY_RUN_REPLAY,
    ACTION_DRY_RUN_PLANNER_HANDOFF,
    ACTION_APPROVAL_REQUIRED_REPAIR,
    ACTION_APPROVAL_REQUIRED_REPLAY,
    ACTION_BLOCKED,
)

GATEWAY_READY = "ready"
GATEWAY_DRY_RUN_ONLY = "dry_run_only"
GATEWAY_APPROVAL_REQUIRED = "approval_required"
GATEWAY_BLOCKED = "blocked"

EXECUTOR_REQUIRED_FIELDS: tuple[str, ...] = (
    "governed_action_execution_id",
    "source_gateway_id",
    "execution_state",
    "execution_allowed",
    "dry_run_only",
    "approval_required",
    "action_results",
    "blocked_actions",
    "review_required_actions",
    "execution_summary",
    "blocking_issues",
    "reason_codes",
)


def governed_runtime_action_executor_states() -> List[str]:
    return list(EXECUTION_STATES)


def governed_runtime_action_executor_action_types() -> List[str]:
    return list(ACTION_TYPES)


def governed_runtime_action_executor_required_fields() -> List[str]:
    return list(EXECUTOR_REQUIRED_FIELDS)


def build_governed_runtime_action_execution_report(
    *,
    gateway_report: Any,
    boundary_report: Any | None = None,
    approval_context: Any | None = None,
    execution_context: Any | None = None,
    dry_run: bool | None = None,
) -> Dict[str, Any]:
    """Build a data-only governed action execution report.

    This module deliberately does not execute subprocesses, mutate files, enqueue
    tasks, or write persistence. It converts an already-built gateway report into
    an execution lifecycle contract that a real executor can enforce later.
    """

    gateway = _mapping(gateway_report)
    boundary = _mapping(boundary_report)
    approval = _mapping(approval_context)
    context = _mapping(execution_context)

    gateway_state = _text(gateway.get("gateway_state"))
    action_requests = [
        copy.deepcopy(item)
        for item in gateway.get("action_requests", [])
        if isinstance(item, dict)
    ]

    effective_dry_run = bool(gateway.get("dry_run_only"))
    if dry_run is not None:
        effective_dry_run = bool(dry_run)

    approval_required = bool(gateway.get("approval_required"))
    boundary_state = _text(boundary.get("boundary_state"))
    boundary_allows = (
        not boundary
        or (
            boundary_state == "boundary_ready"
            and boundary.get("execution_allowed") is True
        )
    )

    blocking_issues: List[Dict[str, Any]] = []
    review_required_actions: List[Dict[str, Any]] = []
    blocked_actions: List[Dict[str, Any]] = []
    action_results: List[Dict[str, Any]] = []

    if not gateway:
        blocking_issues.append({"kind": "gateway_report_missing"})
    elif gateway_state not in {
        GATEWAY_READY,
        GATEWAY_DRY_RUN_ONLY,
        GATEWAY_APPROVAL_REQUIRED,
        GATEWAY_BLOCKED,
    }:
        blocking_issues.append({"kind": "invalid_gateway_state", "gateway_state": gateway_state})

    if gateway_state == GATEWAY_BLOCKED:
        blocking_issues.append({"kind": "gateway_blocked"})

    if boundary and not boundary_allows:
        blocking_issues.append(
            {
                "kind": "boundary_not_ready",
                "boundary_state": boundary_state,
            }
        )

    if not action_requests:
        action_requests = [
            {
                "request_id": "implicit-no-action",
                "request_type": ACTION_NO_ACTION,
                "dry_run_only": effective_dry_run,
                "approval_required": False,
                "execute": False,
            }
        ]

    for index, action in enumerate(action_requests):
        result = _route_action(
            action,
            index=index,
            gateway_state=gateway_state,
            dry_run_only=effective_dry_run,
            approval_required=approval_required,
            boundary_allows=boundary_allows,
            approval_context=approval,
            execution_context=context,
        )
        action_results.append(result)
        if result["action_state"] == EXECUTION_BLOCKED:
            blocked_actions.append(copy.deepcopy(result))
        if result["action_state"] == EXECUTION_REVIEW_REQUIRED:
            review_required_actions.append(copy.deepcopy(result))

    blocking_issues.extend(
        {"kind": "action_blocked", "request_id": _text(item.get("request_id"))}
        for item in blocked_actions
    )

    blocking_issues = _dedupe_issues(blocking_issues)
    review_required = bool(review_required_actions)

    if blocking_issues:
        execution_state = EXECUTION_BLOCKED
        execution_allowed = False
    elif review_required:
        execution_state = EXECUTION_REVIEW_REQUIRED
        execution_allowed = False
    elif effective_dry_run:
        execution_state = EXECUTION_DRY_RUN
        execution_allowed = False
    elif all(item.get("action_state") == EXECUTION_COMPLETED for item in action_results):
        execution_state = EXECUTION_COMPLETED
        execution_allowed = True
    else:
        execution_state = EXECUTION_READY
        execution_allowed = True

    summary = {
        "gateway_state": gateway_state,
        "boundary_state": boundary_state,
        "action_count": len(action_results),
        "blocked_action_count": len(blocked_actions),
        "review_required_action_count": len(review_required_actions),
        "dry_run_only": effective_dry_run,
        "approval_required": approval_required,
        "execution_allowed": execution_allowed,
        "execution_state": execution_state,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "governed_action_execution_id": "",
        "source_gateway_id": _text(gateway.get("gateway_id")),
        "source_boundary_id": _text(boundary.get("boundary_id")),
        "execution_state": execution_state,
        "execution_allowed": execution_allowed,
        "dry_run_only": effective_dry_run,
        "approval_required": approval_required,
        "action_results": action_results,
        "blocked_actions": blocked_actions,
        "review_required_actions": review_required_actions,
        "execution_summary": summary,
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                *_string_list(gateway.get("reason_codes")),
                *_string_list(boundary.get("reason_codes")),
                *_reason_codes_from_issues(blocking_issues),
                *_reason_codes_from_issues(action_results),
                *[
                    code
                    for result in action_results
                    if isinstance(result, dict)
                    for code in _string_list(result.get("reason_codes"))
                ],
            ]
        ),
        "lineage": {
            "source_gateway_id": _text(gateway.get("gateway_id")),
            "source_boundary_id": _text(boundary.get("boundary_id")),
            "input_readiness_id": _text(gateway.get("input_readiness_id")),
        },
        "execution_context": copy.deepcopy(context),
    }
    report["governed_action_execution_id"] = _execution_id(report)
    return report


def validate_governed_runtime_action_execution_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in EXECUTOR_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []

    if _text(payload.get("execution_state")) not in EXECUTION_STATES:
        invalid_fields.append({"field": "execution_state", "reason": "invalid_state"})

    for field in ("execution_allowed", "dry_run_only", "approval_required"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})

    for field in (
        "action_results",
        "blocked_actions",
        "review_required_actions",
        "blocking_issues",
        "reason_codes",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})

    if "execution_summary" in payload and not isinstance(payload.get("execution_summary"), dict):
        invalid_fields.append({"field": "execution_summary", "reason": "expected_dict"})

    for index, result in enumerate(payload.get("action_results", []) if isinstance(payload.get("action_results"), list) else []):
        if not isinstance(result, dict):
            invalid_fields.append({"field": "action_results", "index": index, "reason": "expected_dict"})
            continue
        if _text(result.get("request_type")) not in ACTION_TYPES:
            invalid_fields.append({"field": "action_results", "index": index, "reason": "invalid_request_type"})
        if _text(result.get("action_state")) not in EXECUTION_STATES:
            invalid_fields.append({"field": "action_results", "index": index, "reason": "invalid_action_state"})

    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(EXECUTOR_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def build_governed_runtime_action_execution_summary(execution_report: Any) -> Dict[str, Any]:
    report = _mapping(execution_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "governed_action_execution_id": _text(report.get("governed_action_execution_id")),
        "source_gateway_id": _text(report.get("source_gateway_id")),
        "source_boundary_id": _text(report.get("source_boundary_id")),
        "execution_state": _text(report.get("execution_state")),
        "execution_allowed": bool(report.get("execution_allowed")),
        "dry_run_only": bool(report.get("dry_run_only")),
        "approval_required": bool(report.get("approval_required")),
        "action_count": len(report.get("action_results", []) or []),
        "blocked_action_count": len(report.get("blocked_actions", []) or []),
        "review_required_action_count": len(report.get("review_required_actions", []) or []),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
    }


def _route_action(
    action: Mapping[str, Any],
    *,
    index: int,
    gateway_state: str,
    dry_run_only: bool,
    approval_required: bool,
    boundary_allows: bool,
    approval_context: Mapping[str, Any],
    execution_context: Mapping[str, Any],
) -> Dict[str, Any]:
    request_type = _text(action.get("request_type"))
    request_id = _text(action.get("request_id")) or f"action-{index}"

    issues: List[Dict[str, Any]] = []

    if request_type not in ACTION_TYPES:
        issues.append({"kind": "invalid_action_request_type", "request_type": request_type})

    if action.get("execute") is True:
        issues.append({"kind": "raw_execute_flag_forbidden"})

    if action.get("planner_invoked") is True:
        issues.append({"kind": "planner_invocation_forbidden"})

    if action.get("task_enqueued") is True:
        issues.append({"kind": "task_enqueue_forbidden"})

    if gateway_state == GATEWAY_BLOCKED or request_type == ACTION_BLOCKED:
        issues.append({"kind": "gateway_action_blocked"})

    if not boundary_allows and request_type not in {ACTION_NO_ACTION, ACTION_BLOCKED}:
        issues.append({"kind": "boundary_does_not_allow_action"})

    if approval_required and not _approval_context_valid(approval_context):
        if request_type in {ACTION_APPROVAL_REQUIRED_REPAIR, ACTION_APPROVAL_REQUIRED_REPLAY}:
            action_state = EXECUTION_REVIEW_REQUIRED
        else:
            action_state = EXECUTION_BLOCKED
    elif issues:
        action_state = EXECUTION_BLOCKED
    elif request_type in {ACTION_APPROVAL_REQUIRED_REPAIR, ACTION_APPROVAL_REQUIRED_REPLAY}:
        action_state = EXECUTION_REVIEW_REQUIRED
    elif dry_run_only or request_type in {
        ACTION_DRY_RUN_REPAIR,
        ACTION_DRY_RUN_REPLAY,
        ACTION_DRY_RUN_PLANNER_HANDOFF,
    }:
        action_state = EXECUTION_DRY_RUN
    elif request_type == ACTION_NO_ACTION:
        action_state = EXECUTION_COMPLETED
    else:
        action_state = EXECUTION_READY

    return {
        "request_id": request_id,
        "request_type": request_type,
        "action_state": action_state,
        "execution_performed": False,
        "dry_run_only": bool(dry_run_only or action.get("dry_run_only")),
        "approval_required": bool(approval_required or action.get("approval_required")),
        "boundary_allowed": boundary_allows,
        "reason_codes": _sorted_unique(
            [
                *_string_list(action.get("reason_codes")),
                *_reason_codes_from_issues(issues),
            ]
        ),
        "blocking_issues": _dedupe_issues(issues),
        "execution_context_ref": _text(execution_context.get("execution_context_id")),
    }


def _approval_context_valid(value: Mapping[str, Any]) -> bool:
    if not value:
        return False
    if value.get("approved") is True:
        return True
    if _text(value.get("approval_state")) == "approval_valid":
        return True
    if _text(value.get("state")) in {"approved", "valid"}:
        return True
    return False


def _execution_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_gateway_id": report.get("source_gateway_id"),
        "source_boundary_id": report.get("source_boundary_id"),
        "execution_state": report.get("execution_state"),
        "dry_run_only": report.get("dry_run_only"),
        "approval_required": report.get("approval_required"),
        "action_results": report.get("action_results", []),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-action-execution-" + _stable_hash(payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (dict, bytes)):
        values = list(value)
    else:
        values = []
    return [_text(item) for item in values if _text(item)]


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    if values is None:
        return []
    return sorted({_text(value) for value in values if _text(value)})


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues or []:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()
