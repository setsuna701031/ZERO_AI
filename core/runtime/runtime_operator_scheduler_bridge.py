from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA = (
    "zero.runtime.operator_scheduler_bridge.v1"
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in value if isinstance(item, Mapping)]


def build_scheduler_admission_request(
    *,
    package: Mapping[str, Any],
    run_id: str,
    operator_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a scheduler admission request without importing or mutating scheduler.

    This bridge is intentionally data-only.  It prepares the canonical handoff
    shape that a future scheduler consumer can admit, while keeping the runtime
    operator from directly touching scheduler queues or executor internals.
    """

    result = _mapping(operator_result)
    package_id = _text(package.get("package_id"))
    task_id = _text(package.get("task_id"))
    preserved_run_id = _text(run_id) or _text(result.get("run_id"))
    if not preserved_run_id:
        preserved_run_id = _stable_id("operator-scheduler-run", package_id, task_id)

    requested_changes = _list_of_mappings(package.get("requested_changes"))
    authority_context = _mapping(package.get("authority_context"))

    ready = bool(
        package_id
        and task_id
        and preserved_run_id
        and _text(package.get("goal"))
        and isinstance(package.get("authority_context"), Mapping)
        and isinstance(package.get("requested_changes"), list)
    )

    problems: list[str] = []
    if not package_id:
        problems.append("missing_package_id")
    if not task_id:
        problems.append("missing_task_id")
    if not _text(package.get("goal")):
        problems.append("missing_goal")
    if not isinstance(package.get("authority_context"), Mapping):
        problems.append("missing_authority_context")
    if not isinstance(package.get("requested_changes"), list):
        problems.append("missing_requested_changes")

    request = {
        "schema": RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA,
        "bridge_status": "scheduler_admission_prepared" if ready else "scheduler_admission_blocked",
        "scheduler_ready": ready,
        "scheduler_admission_ready": ready,
        "scheduler_called": False,
        "scheduler_imported": False,
        "queue_mutated": False,
        "direct_queue_mutation": False,
        "direct_scheduler_call_performed": False,
        "package_id": package_id,
        "task_id": task_id,
        "run_id": preserved_run_id,
        "goal": _text(package.get("goal")),
        "requested_mode": _text(package.get("requested_mode")),
        "authority_context": authority_context,
        "requested_changes": requested_changes,
        "operator_ok": bool(result.get("ok") is True) if result else False,
        "operator_controlled_mutation": bool(result.get("controlled_mutation") is True)
        if result
        else False,
        "operator_commit_allowed": bool(result.get("commit_allowed") is True)
        if result
        else False,
        "operator_commit_recorded": bool(result.get("commit_recorded") is True)
        if result
        else False,
        "runtime_commit_apply_status": _text(
            result.get("runtime_commit_apply_status")
        ),
        "non_mainline_issues": list(result.get("non_mainline_issues") or [])
        if result
        else [],
        "problems": problems,
    }
    return request


class RuntimeOperatorSchedulerBridge:
    """Data-only operator-to-scheduler admission bridge."""

    schema = RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA
    scheduler_imported = False
    queue_mutated = False

    def prepare_admission(
        self,
        *,
        package: Mapping[str, Any],
        run_id: str,
        operator_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_scheduler_admission_request(
            package=package,
            run_id=run_id,
            operator_result=operator_result,
        )


__all__ = [
    "RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA",
    "RuntimeOperatorSchedulerBridge",
    "build_scheduler_admission_request",
]
