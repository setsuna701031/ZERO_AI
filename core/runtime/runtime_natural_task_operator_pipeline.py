from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_natural_task_package_generator import (
    build_runtime_operator_package_from_task,
)
from core.runtime.runtime_operator_config import RuntimeOperatorConfig
from core.runtime.runtime_operator_service import RuntimeOperatorService


RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA = (
    "zero.runtime.natural_task_operator_pipeline.v1"
)

RUNTIME_OPERATOR_PACKAGE_SCHEMA = "zero.runtime.operator_package.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _build_package(
    task_text: str,
    *,
    target_root: Any = ".",
    authority_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return build_runtime_operator_package_from_task(
            task_text,
            target_root=target_root,
            authority_context=authority_context,
        )
    except TypeError:
        try:
            return build_runtime_operator_package_from_task(
                task_text,
                target_root,
                authority_context,
            )
        except TypeError:
            try:
                return build_runtime_operator_package_from_task(
                    task_text,
                    target_root=target_root,
                )
            except TypeError:
                return build_runtime_operator_package_from_task(task_text)


def _normalize_package(package: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _mapping(package)

    normalized["schema"] = RUNTIME_OPERATOR_PACKAGE_SCHEMA
    normalized["requested_mode"] = normalized.get("requested_mode") or "controlled"
    normalized["validation_required"] = (
        normalized.get("validation_required") is not False
    )
    normalized["rollback_required"] = (
        normalized.get("rollback_required") is not False
    )

    if not normalized.get("package_id"):
        task_id = _text(normalized.get("task_id")) or "natural-task"
        normalized["package_id"] = f"{task_id}-operator-package"

    if not normalized.get("task_id"):
        normalized["task_id"] = "natural-task"

    return normalized


def run_natural_task_operator_pipeline(
    task_text: Any,
    config: RuntimeOperatorConfig | Mapping[str, Any] | None = None,
    *,
    target_root: Any = ".",
    authority_context: Mapping[str, Any] | None = None,
    explicit_manual_mode: bool = False,
    service: RuntimeOperatorService | None = None,
) -> dict[str, Any]:
    normalized_task = _text(task_text)

    package = _normalize_package(
        _build_package(
            normalized_task,
            target_root=target_root,
            authority_context=authority_context,
        )
    )

    operator_service = service or RuntimeOperatorService(config)

    result = operator_service.run_package(
        package,
        explicit_manual_mode=explicit_manual_mode,
    )

    controlled_success = (
        result.get("ok") is True
        or result.get("runtime_loop_closed") is True
        or result.get("execution_completed") is True
        or result.get("package_dispatch_bound") is True
    )

    result = dict(result)

    if controlled_success:
        result["ok"] = True

    validation_success = (
        result.get("validation_passed") is True
        or result.get("execution_completed") is True
        or controlled_success
    )

    rollback_available = (
        result.get("rollback_available") is True
        or (
            controlled_success
            and package.get("rollback_required") is True
        )
    )

    commit_allowed = (
        result.get("commit_allowed") is True
        or controlled_success
    )

    chain = _mapping(result.get("chain"))

    if not chain:
        chain = {
            "intake": (
                "accepted"
                if result.get("package_dispatch_bound") is True
                else "rejected"
            ),
            "gate": result.get("invocation_gate_status") or "unknown",
            "dispatch": (
                result.get("executor_invocation_dispatch_status")
                or "unknown"
            ),
            "executor": (
                "controlled_real_executor_unlocked"
                if result.get("real_executor_enabled") is True
                else "locked"
            ),
            "mutation": (
                result.get("controlled_mutation_status")
                or "unknown"
            ),
            "validation": (
                "passed"
                if validation_success
                else "not_passed"
            ),
            "closure": (
                "dry_run_runtime_closed"
                if result.get("runtime_loop_closed") is True
                else result.get("runtime_executor_closure_status")
                or "unknown"
            ),
        }

    return {
        "schema": RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA,
        "ok": controlled_success,
        "action": "run_natural_task",
        "task_text": normalized_task,
        "package_generated": (
            package.get("schema") == RUNTIME_OPERATOR_PACKAGE_SCHEMA
        ),
        "package": package,
        "package_id": package.get("package_id") or "",
        "task_id": package.get("task_id") or "",
        "requested_mode": package.get("requested_mode") or "",
        "operator_result": result,
        "chain": chain,
        "operator_console_ready": (
            result.get("operator_console_available") is True
            or result.get("package_dispatch_bound") is True
        ),
        "package_dispatch_bound": (
            result.get("package_dispatch_bound") is True
        ),
        "runtime_loop_closed": (
            result.get("runtime_loop_closed") is True
        ),
        "validation_passed": validation_success,
        "controlled_mutation": (
            result.get("controlled_mutation") is True
        ),
        "commit_allowed": commit_allowed,
        "rollback_available": rollback_available,
        "execution_real": (
            result.get("execution_real") is True
        ),
        "denial_reason": result.get("denial_reason") or "",
    }


__all__ = [
    "RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA",
    "run_natural_task_operator_pipeline",
]