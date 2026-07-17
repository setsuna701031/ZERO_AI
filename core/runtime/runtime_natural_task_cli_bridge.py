from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from core.runtime.runtime_natural_task_package_generator import (
    RUNTIME_OPERATOR_PACKAGE_SCHEMA,
    build_runtime_operator_package_from_task,
    runtime_operator_package_to_summary,
    validate_generated_runtime_operator_package,
)

RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA = "zero.runtime.natural_task_cli_bridge.v1"
_DEFAULT_PYTHON_MODULE = "cli.zero_operator_console"
_DEFAULT_PACKAGE_JSON_PLACEHOLDER = "<generated-runtime-package.json>"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _command_plan(package_json_path: str) -> dict[str, Any]:
    package_path = _text(package_json_path) or _DEFAULT_PACKAGE_JSON_PLACEHOLDER
    argv = [
        "python",
        "-m",
        _DEFAULT_PYTHON_MODULE,
        "run",
        package_path,
        "--controlled",
    ]
    return {
        "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
        "command_status": "planned",
        "argv": argv,
        "display_command": " ".join(argv),
        "package_json_path": package_path,
        "controlled": True,
        "package_json_required": True,
        "package_json_written": False,
        "command_executed": False,
    }


def build_natural_task_cli_bridge(
    task_text: Any,
    *,
    target_root: Any = ".",
    package_json_path: Any = _DEFAULT_PACKAGE_JSON_PLACEHOLDER,
    requested_changes: Sequence[Mapping[str, Any]] | None = None,
    authority_context: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a CLI handoff from natural task text to an operator package.

    The bridge is intentionally planning-only. It builds the package data and a
    deterministic command plan, but it does not start the operator console,
    write package files, or mutate runtime state.
    """

    generation = build_runtime_operator_package_from_task(
        task_text,
        target_root=target_root,
        requested_changes=requested_changes,
        authority_context=authority_context,
        metadata=metadata,
    )
    command = _command_plan(_text(package_json_path))

    if generation.get("ok") is not True:
        return {
            "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
            "ok": False,
            "bridge_status": "denied",
            "denial_reason": generation.get("denial_reason") or "package_generation_denied",
            "runtime_operator_package": None,
            "package_validation": None,
            "package_summary": runtime_operator_package_to_summary(generation),
            "command_plan": command,
            "package_json_written": False,
            "operator_console_started": False,
            "direct_dispatch_requested": False,
            "executor_invoked": False,
            "execution_started": False,
            "task_executed": False,
            "runtime_state_mutated": False,
        }

    package = _mapping(generation.get("runtime_operator_package"))
    validation = validate_generated_runtime_operator_package(package)
    ok = validation.get("valid") is True
    return {
        "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
        "ok": ok,
        "bridge_status": "ready" if ok else "invalid_package",
        "denial_reason": "" if ok else "generated_package_invalid",
        "runtime_operator_package": package,
        "package": deepcopy(package),
        "package_schema": package.get("schema") or "",
        "package_id": package.get("package_id") or "",
        "task_id": package.get("task_id") or "",
        "goal": package.get("goal") or "",
        "requested_mode": package.get("requested_mode") or "",
        "package_validation": validation,
        "package_summary": runtime_operator_package_to_summary(generation),
        "command_plan": command,
        "package_json_written": False,
        "operator_console_started": False,
        "direct_dispatch_requested": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
        "runtime_state_mutated": False,
    }


def natural_task_cli_bridge_to_summary(bridge_result: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(bridge_result)
    package = _mapping(result.get("runtime_operator_package"))
    command = _mapping(result.get("command_plan"))
    return {
        "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
        "ok": result.get("ok") is True,
        "bridge_status": result.get("bridge_status") or "denied",
        "package_schema": package.get("schema") or result.get("package_schema") or "",
        "package_id": package.get("package_id") or result.get("package_id") or "",
        "task_id": package.get("task_id") or result.get("task_id") or "",
        "goal": package.get("goal") or result.get("goal") or "",
        "requested_mode": package.get("requested_mode") or result.get("requested_mode") or "",
        "command_status": command.get("command_status") or "planned",
        "package_json_path": command.get("package_json_path") or "",
        "package_json_written": False,
        "operator_console_started": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
    }


def validate_natural_task_cli_bridge(bridge_result: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(bridge_result)
    errors: list[str] = []

    if result.get("schema") != RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA:
        errors.append("invalid:schema")
    if result.get("ok") is True and result.get("bridge_status") != "ready":
        errors.append("invalid:bridge_status")

    package = _mapping(result.get("runtime_operator_package"))
    if result.get("ok") is True:
        if package.get("schema") != RUNTIME_OPERATOR_PACKAGE_SCHEMA:
            errors.append("invalid:package_schema")
        validation = validate_generated_runtime_operator_package(package)
        if validation.get("valid") is not True:
            errors.append("invalid:runtime_operator_package")

    command = _mapping(result.get("command_plan"))
    if command.get("command_executed") is not False:
        errors.append("invalid:command_executed")
    if result.get("package_json_written") is not False:
        errors.append("invalid:package_json_written")
    if result.get("operator_console_started") is not False:
        errors.append("invalid:operator_console_started")
    if result.get("executor_invoked") is not False:
        errors.append("invalid:executor_invoked")
    if result.get("execution_started") is not False:
        errors.append("invalid:execution_started")
    if result.get("task_executed") is not False:
        errors.append("invalid:task_executed")

    return {
        "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
        "ok": not errors,
        "valid": not errors,
        "errors": errors,
        "bridge_status": result.get("bridge_status") or "denied",
        "package_id": package.get("package_id") or result.get("package_id") or "",
        "task_id": package.get("task_id") or result.get("task_id") or "",
    }


__all__ = [
    "RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA",
    "build_natural_task_cli_bridge",
    "natural_task_cli_bridge_to_summary",
    "validate_natural_task_cli_bridge",
]
