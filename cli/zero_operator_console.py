from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_operator_config import load_runtime_operator_config
from core.runtime.runtime_operator_service import RuntimeOperatorService

try:
    from core.runtime.runtime_governed_mutation_adapter import (
        RuntimeGovernedMutationAdapter,
    )
except Exception:
    RuntimeGovernedMutationAdapter = None  # type: ignore[assignment]

try:
    from core.runtime.runtime_governed_commit_adapter import (
        RuntimeGovernedCommitAdapter,
    )
except Exception:
    RuntimeGovernedCommitAdapter = None  # type: ignore[assignment]

try:
    from core.runtime.runtime_git_commit_actuator import (
        RuntimeGitCommitActuator,
    )
except Exception:
    RuntimeGitCommitActuator = None  # type: ignore[assignment]


OPERATOR_CONSOLE_SCHEMA = "zero.operator_console.v1"


CHAIN_FIELDS = (
    "intake",
    "approval",
    "gate",
    "invocation",
    "dispatch",
    "session",
    "result",
    "closure",
    "executor",
    "mutation",
    "validation",
    "rollback_commit",
)

_RUNS: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class _ConsoleRealExecutorAdapter:
    requested_changes: list[dict[str, Any]]
    safe_no_mutation_adapter: bool = True

    def execute_controlled_no_mutation(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "adapter_status": "completed",
            "mutation_allowed": False,
            "repo_mutation_enabled": False,
            "output_summary": {
                "summary": "operator_console_controlled_executor_complete",
                "requested_changes": list(self.requested_changes),
            },
            "error_summary": {},
            "non_mainline_issues": [],
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _load_package(path: str | Path) -> dict[str, Any]:
    package_path = Path(path)
    try:
        payload = json.loads(package_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"invalid_package_json:{exc.__class__.__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_package_json:object_required")
    return payload


def _validate_package(payload: Mapping[str, Any]) -> list[str]:
    missing = [
        field
        for field in (
            "package_id",
            "task_id",
            "goal",
            "requested_mode",
            "authority_context",
            "requested_changes",
        )
        if not payload.get(field)
    ]
    if missing:
        return [f"missing_{field}" for field in missing]
    if not isinstance(payload.get("authority_context"), Mapping):
        return ["authority_context_object_required"]
    changes = payload.get("requested_changes")
    if not isinstance(changes, list):
        return ["requested_changes_list_required"]
    for change in changes:
        if not isinstance(change, Mapping):
            return ["requested_change_object_required"]
    return []


def _config(package: Mapping[str, Any]) -> dict[str, Any]:
    package_id = _text(package.get("package_id")) or "operator-package"
    return {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": f"workspace/operator_console/{package_id}-checkpoint.json",
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }


def _goal(package: Mapping[str, Any]) -> str:
    return _text(package.get("goal")) or _text(package.get("package_id"))


def _chain_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "intake": "accepted" if result.get("launch_admitted") is True else "rejected",
        "approval": result.get("invocation_approval_status") or "rejected",
        "gate": result.get("invocation_gate_status") or "rejected",
        "invocation": result.get("invocation_record_status") or "rejected",
        "dispatch": result.get("executor_invocation_dispatch_status") or "rejected",
        "session": result.get("runtime_execution_session_start_status") or "rejected",
        "result": result.get("runtime_execution_result_capture_status") or "rejected",
        "closure": result.get("runtime_executor_closure_status") or "rejected",
        "executor": result.get("controlled_real_executor_unlock_status") or "rejected",
        "mutation": result.get("controlled_mutation_status") or "rejected",
        "validation": (
            "passed" if result.get("validation_passed") is True else "not_passed"
        ),
        "rollback_commit": (
            "commit_allowed"
            if result.get("commit_allowed") is True
            else (
                "rollback_completed"
                if result.get("rollback_completed") is True
                else "blocked"
            )
        ),
    }
    return {field: summary[field] for field in CHAIN_FIELDS}


def _workspace_root_for_package(package: Mapping[str, Any]) -> Path:
    package_id = _text(package.get("package_id")) or "operator-package"
    return Path("workspace") / "operator_console" / package_id


def _apply_governed_commit_if_available(
    *,
    package: Mapping[str, Any],
    run_id: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    updated = dict(result)

    if _text(updated.get("runtime_commit_apply_status")) not in {
        "blocked_no_governed_commit_adapter",
        "governed_commit_adapter_unavailable",
    }:
        return updated

    if RuntimeGovernedCommitAdapter is None:
        updated["governed_commit_adapter_attached"] = False
        updated["commit_applied"] = False
        updated["commit_recorded"] = False
        updated["git_diff_recorded"] = False
        updated["runtime_commit_apply_status"] = "blocked_no_governed_commit_adapter"
        updated["denial_reason"] = "governed_commit_adapter_unavailable"
        return updated

    root = _workspace_root_for_package(package)
    adapter = RuntimeGovernedCommitAdapter(report_root=root / "reports")
    adapter_result = adapter.apply_governed_commit(
        runtime_result=updated,
        package_id=_text(package.get("package_id")),
        task_id=_text(package.get("task_id")),
        run_id=run_id,
    )

    if (
        RuntimeGitCommitActuator is not None
        and adapter_result.get("commit_recorded") is True
    ):
        actuator = RuntimeGitCommitActuator(
            repo_root=Path("."),
            report_root=root / "reports",
        )
        git_result = actuator.apply_git_commit(
            governed_commit_record=adapter_result.get("record") or {},
            package_id=_text(package.get("package_id")),
            task_id=_text(package.get("task_id")),
            run_id=run_id,
        )
        adapter_result.update(git_result)

    updated.update(
        {
            "commit_applied": bool(adapter_result.get("commit_applied") is True),
            "commit_recorded": bool(adapter_result.get("commit_recorded") is True),
            "git_diff_recorded": bool(adapter_result.get("git_diff_recorded") is True),
            "governed_commit_adapter_attached": bool(
                adapter_result.get("governed_commit_adapter_attached") is True
            ),
            "runtime_commit_apply_status": _text(
                adapter_result.get("runtime_commit_apply_status")
            ),
            "commit_id": _text(adapter_result.get("commit_id")),
            "denial_reason": _text(adapter_result.get("denial_reason")),
            "governed_commit_record_path": _text(adapter_result.get("record_path")),
            "git_commit_actuator_record_path": _text(
                adapter_result.get("git_commit_actuator_record_path")
            ),
        }
    )
    return updated


def _status_payload(
    *,
    package: Mapping[str, Any],
    run_id: str,
    mode: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    chain = _chain_summary(result)
    return {
        "schema": OPERATOR_CONSOLE_SCHEMA,
        "ok": result.get("ok") is True,
        "operator_console_available": True,
        "web_ui_available": False,
        "run_id": run_id,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "requested_mode": _text(package.get("requested_mode")),
        "console_mode": mode,
        "chain": chain,
        "runtime_loop_closed": bool(
            result.get("runtime_executor_closure_status") == "dry_run_runtime_closed"
        ),
        "controlled_mutation_available": True,
        "mutation_allowed": bool(result.get("mutation_allowed") is True),
        "real_executor_enabled": bool(result.get("real_executor_enabled") is True),
        "execution_real": bool(result.get("execution_real") is True),
        "controlled_mutation": bool(result.get("controlled_mutation") is True),
        "validation_required": bool(result.get("validation_required") is True),
        "rollback_available": bool(result.get("rollback_available") is True),
        "validation_passed": bool(result.get("validation_passed") is True),
        "rollback_completed": bool(result.get("rollback_completed") is True),
        "commit_allowed": bool(result.get("commit_allowed") is True),
        "commit_applied": bool(result.get("commit_applied") is True),
        "commit_recorded": bool(result.get("commit_recorded") is True),
        "commit_id": _text(result.get("commit_id")),
        "git_diff_recorded": bool(result.get("git_diff_recorded") is True),
        "runtime_commit_apply_status": _text(
            result.get("runtime_commit_apply_status")
        ),
        "governed_mutation_adapter_attached": bool(
            result.get("governed_mutation_adapter_attached") is True
        ),
        "governed_commit_adapter_attached": bool(
            result.get("governed_commit_adapter_attached") is True
        ),
        "governed_commit_record_path": _text(
            result.get("governed_commit_record_path")
        ),
        "git_commit_actuator_record_path": _text(
            result.get("git_commit_actuator_record_path")
        ),
        "denial_reason": _text(result.get("denial_reason")),
        "non_mainline_issues": list(result.get("non_mainline_issues") or []),
    }


def _run_service(package: Mapping[str, Any], *, mode: str) -> dict[str, Any]:
    adapters: dict[str, Any] = {}
    if mode == "controlled":
        adapters["controlled_real_executor_adapter"] = _ConsoleRealExecutorAdapter(
            requested_changes=[dict(item) for item in package.get("requested_changes") or []]
        )
        if RuntimeGovernedMutationAdapter is not None:
            root = _workspace_root_for_package(package)
            adapters["controlled_mutation_adapter"] = RuntimeGovernedMutationAdapter(
                workspace_root=root / "workspace",
                sandbox_source_root=root / "sandbox",
                rollback_root=root / "rollback",
                report_root=root / "reports",
            )
    service = RuntimeOperatorService(_config(package), **adapters)
    return service.run_goal(_goal(package), explicit_manual_mode=True)


def _record_run(
    *,
    package: Mapping[str, Any],
    mode: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    run_id = _stable_id(
        "operator-console-run",
        package.get("package_id"),
        package.get("task_id"),
        mode,
    )
    final_result = (
        _apply_governed_commit_if_available(
            package=package,
            run_id=run_id,
            result=result,
        )
        if mode == "controlled"
        else dict(result)
    )
    payload = _status_payload(
        package=package,
        run_id=run_id,
        mode=mode,
        result=final_result,
    )
    _RUNS[run_id] = {
        "package": dict(package),
        "result": dict(final_result),
        "summary": payload,
    }
    return payload


def submit_package(package_json: str | Path) -> dict[str, Any]:
    package = _load_package(package_json)
    problems = _validate_package(package)
    if problems:
        return {
            "schema": OPERATOR_CONSOLE_SCHEMA,
            "ok": False,
            "operator_console_available": True,
            "web_ui_available": False,
            "command": "submit",
            "run_id": "",
            "package_id": _text(package.get("package_id")),
            "denial_reason": "invalid_package",
            "non_mainline_issues": problems,
            "chain": {field: "rejected" for field in CHAIN_FIELDS},
        }
    result = _run_service(package, mode="submit")
    payload = _record_run(package=package, mode="submit", result=result)
    payload["command"] = "submit"
    return payload


def run_package(package_json: str | Path, *, controlled: bool = False) -> dict[str, Any]:
    package = _load_package(package_json)
    problems = _validate_package(package)
    if problems:
        return {
            "schema": OPERATOR_CONSOLE_SCHEMA,
            "ok": False,
            "operator_console_available": True,
            "web_ui_available": False,
            "command": "run",
            "run_id": "",
            "package_id": _text(package.get("package_id")),
            "denial_reason": "invalid_package",
            "non_mainline_issues": problems,
            "chain": {field: "rejected" for field in CHAIN_FIELDS},
            "mutation_allowed": False,
        }
    mode = "controlled" if controlled else "dry_run"
    result = _run_service(package, mode=mode)
    payload = _record_run(package=package, mode=mode, result=result)
    payload["command"] = "run"
    if not controlled:
        payload["mutation_allowed"] = False
    return payload


def status_run(run_id: str) -> dict[str, Any]:
    record = _RUNS.get(_text(run_id))
    if not record:
        return {
            "schema": OPERATOR_CONSOLE_SCHEMA,
            "ok": False,
            "operator_console_available": True,
            "web_ui_available": False,
            "command": "status",
            "run_id": _text(run_id),
            "denial_reason": "run_not_found",
            "chain": {field: "unavailable" for field in CHAIN_FIELDS},
            "non_mainline_issues": ["latest_runtime_status_unavailable"],
        }
    summary = dict(record["summary"])
    summary["command"] = "status"
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-console")
    commands = parser.add_subparsers(dest="command", required=True)

    submit = commands.add_parser("submit")
    submit.add_argument("package_json")

    status = commands.add_parser("status")
    status.add_argument("run_id")

    run = commands.add_parser("run")
    run.add_argument("package_json")
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--controlled", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "submit":
        result = submit_package(args.package_json)
    elif args.command == "status":
        result = status_run(args.run_id)
    else:
        result = run_package(args.package_json, controlled=args.controlled)
    _print_json(result)
    return 0 if result.get("ok") or result.get("command") in {"submit", "status", "run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHAIN_FIELDS",
    "OPERATOR_CONSOLE_SCHEMA",
    "build_parser",
    "main",
    "run_package",
    "status_run",
    "submit_package",
]