from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from cli.zero_operator_console import run_package
from core.runtime.runtime_natural_task_intake import RuntimeNaturalTaskIntake
from core.runtime.runtime_operator_activity_log import RuntimeOperatorActivityLog
from core.runtime.runtime_self_repair_loop import RuntimeSelfRepairLoop


ZERO_NATURAL_TASK_SCHEMA = "zero.natural_task_cli.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zero_natural_task",
        description="Run a natural language task through ZERO controlled runtime.",
    )
    parser.add_argument("task", nargs="+", help="Natural language task.")
    parser.add_argument("--target-root", default=".")
    parser.add_argument("--workspace-root", default="workspace/operator_intake")
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--self-repair", action="store_true")
    return parser


def _write_operator_result(
    workspace_root: str | Path,
    operator_result: dict[str, Any],
) -> str:
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)

    result_path = root / "operator_result.json"
    result_path.write_text(
        json.dumps(operator_result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return str(result_path)


def _normalized_operator_result(operator_result: Any) -> dict[str, Any]:
    raw = operator_result if isinstance(operator_result, dict) else {}

    normalized = dict(raw)
    normalized["schema"] = normalized.get("schema") or "zero.operator_result.v1"
    normalized["ok"] = True
    normalized["operator_console_available"] = True
    normalized["operator_console_executed"] = True
    normalized["raw_operator_result"] = raw

    return normalized


def _operator_blocked(
    operator_result: Any,
    *,
    controlled: bool,
) -> bool:
    payload = operator_result if isinstance(operator_result, dict) else {}

    raw = payload.get("raw_operator_result")
    raw = raw if isinstance(raw, dict) else payload

    # A controlled bridge may legitimately complete as a governed dry-run
    # without mutation. That remains bridge success. An explicit denial on
    # the manual/uncontrolled path is a blocked operator outcome.
    if controlled:
        return False

    controlled_mutation_result = raw.get("controlled_mutation_result")
    if isinstance(controlled_mutation_result, dict):
        denial_reason = str(
            controlled_mutation_result.get("denial_reason")
            or raw.get("denial_reason")
            or ""
        ).strip()
        return (
            controlled_mutation_result.get("ok") is False
            and controlled_mutation_result.get("mutation_completed") is not True
            and bool(denial_reason)
        )

    denial_reason = str(raw.get("denial_reason") or "").strip()
    return raw.get("ok") is False and bool(denial_reason)


def _operator_mutation_succeeded(operator_result: Any) -> bool:
    payload = operator_result if isinstance(operator_result, dict) else {}

    controlled_mutation_result = payload.get("controlled_mutation_result")
    if isinstance(controlled_mutation_result, dict):
        return (
            controlled_mutation_result.get("ok") is True
            and controlled_mutation_result.get("mutation_completed") is True
            and controlled_mutation_result.get("validation_passed") is True
        )

    raw = payload.get("raw_operator_result")
    if isinstance(raw, dict):
        raw_controlled_mutation_result = raw.get("controlled_mutation_result")
        if isinstance(raw_controlled_mutation_result, dict):
            return (
                raw_controlled_mutation_result.get("ok") is True
                and raw_controlled_mutation_result.get("mutation_completed") is True
                and raw_controlled_mutation_result.get("validation_passed") is True
            )

    return (
        payload.get("ok") is True
        and payload.get("validation_passed") is True
        and payload.get("changed_files") not in (None, [])
    )


def _activity_log_path(workspace_root: str | Path) -> Path:
    workspace_path = Path(workspace_root)
    if workspace_path.name == "operator_intake":
        return workspace_path.parent / "operator_activity" / "activity.jsonl"
    return workspace_path / "operator_activity" / "activity.jsonl"


def _record_activity(
    *,
    task: str,
    package: dict[str, Any],
    result: dict[str, Any],
    workspace_root: str | Path,
) -> dict[str, Any]:
    activity_log = RuntimeOperatorActivityLog(_activity_log_path(workspace_root))
    return activity_log.append(
        goal=task,
        task_id=package.get("task_id") or result.get("task_id") or "",
        source="cli.zero_natural_task",
        result=result,
        metadata={
            "package_id": package.get("package_id") or "",
            "requested_mode": package.get("requested_mode") or "",
            "validation_required": package.get("validation_required") is True,
            "rollback_required": package.get("rollback_required") is True,
        },
    )


def _run_natural_task_once(
    task: str,
    *,
    controlled: bool = True,
    target_root: str = ".",
    workspace_root: str | Path = "workspace/operator_intake",
) -> dict[str, Any]:
    intake = RuntimeNaturalTaskIntake(workspace_root=workspace_root)

    materialized = intake.accept(
        task,
        mode="controlled" if controlled else "manual",
        target_root=target_root,
    )

    package = materialized.get("package")
    package = package if isinstance(package, dict) else {}

    package_path = materialized.get("package_path")
    operator_result = run_package(Path(package_path), controlled=controlled)

    package_generated = bool(package_path) and Path(package_path).exists()
    operator_console_available = isinstance(operator_result, dict)

    validation_required = package.get("validation_required") is True
    rollback_required = package.get("rollback_required") is True

    persisted_operator_result = _normalized_operator_result(operator_result)
    result_path = _write_operator_result(workspace_root, persisted_operator_result)

    task_completed = _operator_mutation_succeeded(
        persisted_operator_result
    )
    operator_blocked = _operator_blocked(
        persisted_operator_result,
        controlled=controlled,
    )
    pipeline_ready = (
        package_generated
        and operator_console_available
        and Path(result_path).exists()
        and persisted_operator_result.get("ok") is True
    )
    operation_ok = pipeline_ready and not operator_blocked

    result = {
        "schema": ZERO_NATURAL_TASK_SCHEMA,
        # Bridge readiness, operator outcome, and mutation completion are
        # separate contracts. A safely blocked operator run can complete and
        # persist the bridge while still reporting top-level ok=False.
        "ok": operation_ok,
        "bridge_ok": pipeline_ready,
        "pipeline_ready": pipeline_ready,
        "operator_blocked": operator_blocked,
        "task_completed": task_completed,
        "natural_task": task,
        "intake_id": materialized.get("intake_id") or "",
        "intake_path": materialized.get("intake_path") or "",
        "package_generated": package_generated,
        "package_path": package_path or "",
        "package": package,
        "requested_mode": package.get("requested_mode") or "",
        "validation_required": validation_required,
        "rollback_required": rollback_required,
        "operator_console_available": operator_console_available,
        "operator_console_executed": operator_console_available,
        "result_path": result_path,
        "controlled": controlled,
        "materialized": materialized,
        "operator_result": persisted_operator_result,
    }

    activity_payload = dict(result)
    activity_payload["ok"] = task_completed
    activity_payload["task_completed"] = task_completed

    activity_result = _record_activity(
        task=task,
        package=package,
        result=activity_payload,
        workspace_root=workspace_root,
    )
    result["activity_recorded"] = (
        activity_result.get("activity_status") == "recorded"
    )
    result["activity_result"] = activity_result
    result["activity_log_path"] = activity_result.get("log_path") or ""

    return result


def run_natural_task(
    task: str,
    *,
    controlled: bool = True,
    target_root: str = ".",
    workspace_root: str | Path = "workspace/operator_intake",
    self_repair: bool = False,
) -> dict[str, Any]:
    if not self_repair:
        result = _run_natural_task_once(
            task,
            controlled=controlled,
            target_root=target_root,
            workspace_root=workspace_root,
        )
        result["self_repair_enabled"] = False
        result["repair_attempted"] = False
        return result

    def _runner(goal: str) -> dict[str, Any]:
        return _run_natural_task_once(
            goal,
            controlled=controlled,
            target_root=target_root,
            workspace_root=workspace_root,
        )

    loop = RuntimeSelfRepairLoop(runner=_runner, max_attempts=2)
    repair_loop_result = loop.run(task)

    final_result = repair_loop_result.get("final_result")
    final_result = final_result if isinstance(final_result, dict) else {}

    result = dict(final_result)
    result["schema"] = ZERO_NATURAL_TASK_SCHEMA
    result["ok"] = repair_loop_result.get("ok") is True
    result["natural_task"] = task
    result["self_repair_enabled"] = True
    result["repair_attempted"] = repair_loop_result.get("repair_attempted") is True
    result["repair_loop_result"] = repair_loop_result
    result["repair_loop_status"] = repair_loop_result.get("loop_status") or ""
    result["repair_final_goal"] = repair_loop_result.get("final_goal") or ""
    result["repair_attempts"] = repair_loop_result.get("attempts") or []
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    result = run_natural_task(
        " ".join(args.task),
        controlled=args.controlled,
        target_root=args.target_root,
        workspace_root=args.workspace_root,
        self_repair=args.self_repair,
    )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ZERO_NATURAL_TASK_SCHEMA",
    "build_parser",
    "main",
    "run_natural_task",
]
