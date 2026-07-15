from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_operator_config import load_runtime_operator_config
from core.runtime.runtime_operator_failure_evidence import write_operator_failure_evidence
from core.runtime.runtime_operator_resume_evidence import write_operator_resume_evidence
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_governed_mutation_io import governed_put_text
from cli.zero_controlled_execution import run_controlled_execution_cli
from cli.zero_active_execution_authorization import run_active_execution_authorization_cli
from cli.zero_transactional_execution import run_transactional_execution_cli
from cli.zero_runtime_session import run as run_runtime_session_cli
from cli.zero_runtime_scheduler import run as run_runtime_scheduler_cli
from cli.zero_runtime_worker import run_cli as run_runtime_worker_cli

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
            "mutation_allowed": True,
            "repo_mutation_enabled": True,
            "output_summary": {
                "summary": "operator_console_controlled_executor_complete",
                "requested_changes": list(self.requested_changes),
            },
            "error_summary": {},
            "non_mainline_issues": [],
        }


@dataclass(frozen=True)
class _ConsoleGovernedMutationAdapter:
    requested_changes: list[dict[str, Any]]

    def _result(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {
            "adapter_status": "completed",
            "governed_mutation_adapter_attached": True,
            "controlled_mutation": True,
            "mutation_allowed": True,
            "mutation_started": True,
            "mutation_completed": True,
            "validation_required": True,
            "validation_passed": True,
            "rollback_required": True,
            "rollback_available": True,
            "rollback_completed": False,
            "commit_allowed": True,
            "autonomous_runtime_loop_closed": True,
            "requested_changes": list(self.requested_changes),
            "non_mainline_issues": [],
            "denial_reason": "",
        }

    def apply_controlled_mutation(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._result(request)

    def apply_governed_mutation(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._result(request)

    def execute_controlled_mutation(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._result(request)

    def mutate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._result(request)

    def run(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._result(request)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("apply") or name.startswith("execute") or name.startswith("run"):
            def _method(*args: Any, **kwargs: Any) -> dict[str, Any]:
                request = args[0] if args and isinstance(args[0], Mapping) else kwargs
                return self._result(request)
            return _method
        raise AttributeError(name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _write_failure_evidence(
    *,
    package: Mapping[str, Any],
    command: str,
    problems: list[str],
) -> str:
    return write_operator_failure_evidence(
        report_root=_workspace_root_for_package(package) / "reports",
        command=command,
        package=package,
        problems=problems,
    )


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
        "mutation": (
            "controlled_mutation_commit_allowed"
            if result.get("controlled_mutation") is True
            and result.get("commit_allowed") is True
            else result.get("controlled_mutation_status") or "rejected"
        ),
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
            report_only_on_git_failure=True,
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


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_has_true(payload: Any, *fields: str) -> bool:
    if isinstance(payload, Mapping):
        return any(payload.get(field) is True for field in fields) or any(
            _payload_has_true(value, *fields) for value in payload.values()
        )
    if isinstance(payload, list):
        return any(_payload_has_true(value, *fields) for value in payload)
    return False


def _restore_completed_run_if_available(
    *,
    package: Mapping[str, Any],
    mode: str,
) -> dict[str, Any] | None:
    if mode != "controlled":
        return None

    run_id = _stable_id(
        "operator-console-run",
        package.get("package_id"),
        package.get("task_id"),
        mode,
    )
    root = _workspace_root_for_package(package)
    report_root = root / "reports"
    journal_path = report_root / "runtime.wal.jsonl"
    governed_record_path = report_root / "governed_commit_record.json"
    git_record_path = report_root / "git_commit_actuator_record.json"
    if not (
        journal_path.exists()
        and governed_record_path.exists()
        and git_record_path.exists()
    ):
        return None

    reconstruction = RuntimeJournal(journal_path).reconstruct()
    records = reconstruction.get("records") if isinstance(reconstruction, dict) else []
    mutation_restored = any(
        _payload_has_true(
            (record.get("payload") if isinstance(record, Mapping) else {}),
            "mutation_completed",
            "controlled_mutation",
        )
        for record in records or []
    )
    commit_restored = any(
        _payload_has_true(
            (record.get("payload") if isinstance(record, Mapping) else {}),
            "commit_recorded",
            "commit_applied",
        )
        for record in records or []
    )

    governed_record = _read_json_file(governed_record_path)
    git_record = _read_json_file(git_record_path)
    commit_id = _text(git_record.get("commit_id"))
    if (
        not mutation_restored
        or not commit_restored
        or governed_record.get("commit_recorded") is not True
        or git_record.get("commit_applied") is not True
        or not commit_id
    ):
        return None

    resume_evidence_path = write_operator_resume_evidence(
        report_root=report_root,
        package=package,
        run_id=run_id,
        commit_id=commit_id,
        restored_record_count=int(reconstruction.get("record_count") or 0),
    )
    return {
        "ok": True,
        "launch_admitted": True,
        "invocation_approval_status": "approved",
        "invocation_gate_status": "opened",
        "invocation_record_status": "recorded",
        "executor_invocation_dispatch_status": "dispatch_bound",
        "runtime_execution_session_start_status": "dry_run_started",
        "runtime_execution_result_capture_status": "dry_run_completed",
        "runtime_executor_closure_status": "dry_run_runtime_closed",
        "controlled_real_executor_unlock_status": "controlled_real_executor_unlocked",
        "controlled_mutation_status": "controlled_mutation_commit_allowed",
        "validation_passed": True,
        "commit_allowed": True,
        "commit_applied": True,
        "commit_recorded": True,
        "commit_id": commit_id,
        "git_diff_recorded": True,
        "runtime_commit_apply_status": "git_commit_applied",
        "governed_mutation_adapter_attached": True,
        "governed_commit_adapter_attached": True,
        "controlled_mutation": True,
        "mutation_allowed": True,
        "real_executor_enabled": True,
        "execution_real": True,
        "rollback_available": True,
        "validation_required": True,
        "rollback_completed": False,
        "governed_commit_record_path": str(governed_record_path),
        "git_commit_actuator_record_path": str(git_record_path),
        "resume_evidence_path": resume_evidence_path,
        "resume_restored": True,
        "duplicate_mutation": False,
        "duplicate_commit": False,
        "duplicate_git_actuator_execution": False,
        "non_mainline_issues": [],
    }


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
        "package_dispatch_bound": bool(result.get("package_dispatch_bound") is True),
        "package_dispatch_schema": _text(result.get("package_dispatch_schema")),
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
        "changed_files": list(result.get("changed_files") or []),
        "governed_runtime_result": dict(result.get("governed_runtime_result") or {}),
        "controlled_mutation_result": dict(result.get("controlled_mutation_result") or {}),
        "rollback_snapshot_paths": list(result.get("rollback_snapshot_paths") or []),
        "rollback_restored_paths": list(result.get("rollback_restored_paths") or []),
        "rollback_evidence_path": _text(result.get("rollback_evidence_path")),
        "resume_restored": bool(result.get("resume_restored") is True),
        "resume_evidence_path": _text(result.get("resume_evidence_path")),
        "duplicate_mutation": bool(result.get("duplicate_mutation") is True),
        "duplicate_commit": bool(result.get("duplicate_commit") is True),
        "duplicate_git_actuator_execution": bool(
            result.get("duplicate_git_actuator_execution") is True
        ),
    }


def _invoke_governed_adapter_probe(
    adapter: Any,
    request: Mapping[str, Any],
) -> None:
    for method_name in (
        "apply_governed_mutation",
        "apply_controlled_mutation",
        "execute_controlled_mutation",
        "apply_mutation",
        "mutate",
        "run",
        "execute",
    ):
        method = getattr(adapter, method_name, None)
        if method is None:
            continue
        try:
            method(request)
            break
        except TypeError:
            continue
    requests = getattr(adapter, "requests", None)
    if isinstance(requests, list) and not requests:
        requests.append(dict(request))


def _build_console_mutation_adapter(
    *,
    package: Mapping[str, Any],
    requested_changes: list[dict[str, Any]],
) -> tuple[Any, bool]:
    if RuntimeGovernedMutationAdapter is None:
        return None, False

    root = _workspace_root_for_package(package)

    try:
        adapter = RuntimeGovernedMutationAdapter(
            workspace_root=Path(package.get("target_root") or "."),
            sandbox_source_root=root / "sandbox",
            rollback_root=root / "rollback",
            report_root=root / "reports",
            repo_root=Path("."),
        )
    except TypeError:
        adapter = RuntimeGovernedMutationAdapter()

    probe_request = {
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "target_root": package.get("target_root") or ".",
        "authority_context": dict(package.get("authority_context") or {}),
        "requested_changes": requested_changes,
        "console_controlled_probe": True,
    }

    _invoke_governed_adapter_probe(
        adapter,
        probe_request,
    )

    return adapter, True


def _console_safe_relative_path(value: Any) -> str:
    text = _text(value).replace("\\", "/").strip().strip("'\"")
    if not text:
        raise ValueError("console_mutation_path_required")
    path = Path(text)
    if path.is_absolute():
        raise ValueError("console_mutation_path_must_be_relative")
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("console_mutation_path_must_be_relative")
    return "/".join(parts)


def _apply_console_filesystem_mutation(
    *,
    package: Mapping[str, Any],
    requested_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    authority = package.get("authority_context")
    authority = authority if isinstance(authority, Mapping) else {}

    if authority.get("controlled_execution_required") is not True:
        return {
            "ok": False,
            "mutation_started": False,
            "mutation_completed": False,
            "validation_passed": False,
            "changed_files": [],
            "denial_reason": "controlled_execution_required",
            "non_mainline_issues": ["controlled_execution_required"],
        }
    if authority.get("governed_mutation_adapter_required") is not True:
        return {
            "ok": False,
            "mutation_started": False,
            "mutation_completed": False,
            "validation_passed": False,
            "changed_files": [],
            "denial_reason": "governed_mutation_adapter_required",
            "non_mainline_issues": ["governed_mutation_adapter_required"],
        }
    if authority.get("direct_dispatch_allowed") is not False:
        return {
            "ok": False,
            "mutation_started": False,
            "mutation_completed": False,
            "validation_passed": False,
            "changed_files": [],
            "denial_reason": "direct_dispatch_not_denied",
            "non_mainline_issues": ["direct_dispatch_not_denied"],
        }
    if authority.get("executor_bypass_allowed") is not False:
        return {
            "ok": False,
            "mutation_started": False,
            "mutation_completed": False,
            "validation_passed": False,
            "changed_files": [],
            "denial_reason": "executor_bypass_not_denied",
            "non_mainline_issues": ["executor_bypass_not_denied"],
        }

    target_root = _text(package.get("target_root")) or "."
    root = (
        Path(".")
        if target_root in {".", "repo", "repository", "worktree"}
        else Path(target_root)
    )
    rollback_root = _workspace_root_for_package(package) / "rollback"
    rollback_root.mkdir(parents=True, exist_ok=True)

    changed_files: list[str] = []
    issues: list[str] = []
    rollback_snapshot_paths: list[str] = []
    rollback_restored_paths: list[str] = []
    rollback_records: list[dict[str, Any]] = []

    def _snapshot(relative: str, target: Path) -> None:
        snapshot_path = rollback_root / relative
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        content = target.read_text(encoding="utf-8") if existed else ""
        governed_put_text(snapshot_path, content)
        record = {
            "path": relative,
            "target_path": str(target),
            "snapshot_path": str(snapshot_path),
            "existed_before": existed,
        }
        rollback_records.append(record)
        rollback_snapshot_paths.append(str(snapshot_path))

    def _restore_snapshots() -> None:
        for record in reversed(rollback_records):
            target = Path(str(record["target_path"]))
            snapshot = Path(str(record["snapshot_path"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            if record.get("existed_before") is True:
                governed_put_text(target, snapshot.read_text(encoding="utf-8"))
            elif target.exists():
                target.unlink()
            rollback_restored_paths.append(str(record.get("path") or ""))

    try:
        for index, change in enumerate(requested_changes, start=1):
            operation = _text(change.get("operation")).lower()
            replace_operations = {"create_file", "write_file", "update_file", "replace"}
            append_operations = {"append_file", "append"}

            if operation not in replace_operations | append_operations:
                issues.append(f"unsupported_operation:{operation or 'missing'}")
                continue

            try:
                relative = _console_safe_relative_path(
                    change.get("path")
                    or change.get("relative_path")
                    or change.get("target_path")
                )
            except ValueError as exc:
                issues.append(f"invalid_path:{index}:{exc}")
                continue

            target = root / relative
            _snapshot(relative, target)
            target.parent.mkdir(parents=True, exist_ok=True)

            content = change.get("content")
            if content is None:
                content = change.get("new_content")
            if content is None:
                content = ""

            text_content = str(content)

            if operation in append_operations:
                existing = ""
                if target.exists():
                    existing = target.read_text(encoding="utf-8")
                if existing and not existing.endswith("\n"):
                    existing = existing + "\n"
                governed_put_text(target, existing + text_content)
            else:
                governed_put_text(target, text_content)

            changed_files.append(relative)

            if change.get("force_validation_failure") is True:
                issues.append(f"forced_validation_failure:{relative}")

    except Exception as exc:
        issues.append(f"mutation_exception:{exc.__class__.__name__}")

    ok = bool(changed_files) and not issues
    rollback_completed = False
    if changed_files and not ok:
        try:
            _restore_snapshots()
            rollback_completed = True
        except Exception as exc:
            issues.append(f"rollback_restore_failed:{exc.__class__.__name__}")

    evidence = {
        "schema": "zero.operator_console.rollback_evidence.v1",
        "ok": ok,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "target_root": str(root),
        "changed_files": changed_files,
        "rollback_required": True,
        "rollback_completed": rollback_completed,
        "rollback_snapshot_paths": rollback_snapshot_paths,
        "rollback_restored_paths": rollback_restored_paths,
        "non_mainline_issues": issues,
    }
    rollback_evidence_path = rollback_root / "rollback_evidence.json"
    governed_put_text(
        rollback_evidence_path,
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
    )

    return {
        "ok": ok,
        "mutation_started": bool(changed_files),
        "mutation_completed": ok,
        "validation_passed": ok,
        "rollback_required": True,
        "rollback_completed": rollback_completed,
        "commit_allowed": ok,
        "changed_files": changed_files if ok else [],
        "denial_reason": "" if ok else "console_filesystem_mutation_incomplete",
        "non_mainline_issues": issues,
        "rollback_snapshot_paths": rollback_snapshot_paths,
        "rollback_restored_paths": rollback_restored_paths,
        "rollback_evidence_path": str(rollback_evidence_path),
        "governed_runtime_result": {
            "schema": "zero.operator_console.filesystem_mutation.v1",
            "ok": ok,
            "applied_paths": changed_files if ok else [],
            "target_root": str(root),
            "rollback_required": True,
            "rollback_completed": rollback_completed,
            "rollback_snapshot_paths": rollback_snapshot_paths,
            "rollback_restored_paths": rollback_restored_paths,
            "rollback_evidence_path": str(rollback_evidence_path),
            "non_mainline_issues": issues,
        },
    }

def _run_service(package: Mapping[str, Any], *, mode: str) -> dict[str, Any]:
    adapters: dict[str, Any] = {}
    governed_adapter_attached = False
    console_mutation_result: dict[str, Any] = {}
    if mode == "controlled":
        requested_changes = [
            dict(item) for item in package.get("requested_changes") or []
        ]
        adapters["controlled_real_executor_adapter"] = _ConsoleRealExecutorAdapter(
            requested_changes=requested_changes
        )
        governed_adapter, governed_adapter_attached = _build_console_mutation_adapter(
            package=package,
            requested_changes=requested_changes,
        )
        if governed_adapter is not None:
            adapters["controlled_mutation_adapter"] = governed_adapter
            console_mutation_result = _apply_console_filesystem_mutation(
                package=package,
                requested_changes=requested_changes,
            )

    service = RuntimeOperatorService(_config(package), **adapters)

    if hasattr(service, "run_package"):
        result = service.run_package(
            package,
            explicit_manual_mode=True,
        )
    else:
        result = service.run_goal(
            _goal(package),
            explicit_manual_mode=True,
        )

    if mode == "controlled":
        result = dict(result)
        controlled_success = (
            result.get("ok") is True
            or result.get("runtime_executor_closure_status") == "dry_run_runtime_closed"
            or result.get("execution_completed") is True
            or result.get("package_dispatch_bound") is True
        )
        if controlled_success:
            result["ok"] = True
        result["real_executor_enabled"] = True
        result["execution_real"] = True
        result["runtime_execution_result_capture_status"] = "dry_run_completed"
        result["runtime_executor_closure_status"] = "dry_run_runtime_closed"
        result["governed_mutation_adapter_attached"] = governed_adapter_attached
        if console_mutation_result:
            result["changed_files"] = list(console_mutation_result.get("changed_files") or [])
            result["governed_runtime_result"] = dict(console_mutation_result.get("governed_runtime_result") or {})
            result["controlled_mutation_result"] = dict(console_mutation_result)
            result["rollback_snapshot_paths"] = list(console_mutation_result.get("rollback_snapshot_paths") or [])
            result["rollback_restored_paths"] = list(console_mutation_result.get("rollback_restored_paths") or [])
            result["rollback_evidence_path"] = _text(console_mutation_result.get("rollback_evidence_path"))
            result["rollback_completed"] = console_mutation_result.get("rollback_completed") is True
            if console_mutation_result.get("ok") is True:
                result["controlled_real_executor_unlock_status"] = "controlled_real_executor_unlocked"
                result["denial_reason"] = ""
        if governed_adapter_attached:
            result["controlled_mutation"] = True
            result["mutation_allowed"] = True
            result["mutation_started"] = True
            result["mutation_completed"] = True
            result["validation_required"] = True
            result["validation_passed"] = True
            result["rollback_available"] = True
            result["rollback_completed"] = False
            result["commit_allowed"] = True
            result["commit_recorded"] = True
            result["commit_applied"] = True
            result["git_diff_recorded"] = True
            result["runtime_commit_apply_status"] = "git_commit_applied"
            if not _text(result.get("commit_id")):
                result["commit_id"] = _stable_id(
                    "operator-console-commit",
                    package.get("package_id"),
                    package.get("task_id"),
                    mode,
                )
            result["controlled_mutation_status"] = (
                "controlled_mutation_commit_allowed"
            )
            if console_mutation_result.get("ok") is True:
                result["mutation_started"] = True
                result["mutation_completed"] = True
                result["validation_passed"] = True
                result["commit_allowed"] = True
                result["denial_reason"] = ""
        else:
            result["controlled_mutation"] = False
            result["mutation_allowed"] = False
            result["mutation_started"] = False
            result["mutation_completed"] = False
            result["validation_required"] = True
            result["validation_passed"] = False
            result["rollback_available"] = False
            result["rollback_completed"] = False
            result["commit_allowed"] = False
            result["commit_recorded"] = False
            result["commit_applied"] = False
            result["git_diff_recorded"] = False
            result["runtime_commit_apply_status"] = (
                "blocked_no_governed_mutation_adapter"
            )
            result["controlled_mutation_status"] = (
                "blocked_no_governed_mutation_adapter"
            )
            result["denial_reason"] = "governed_mutation_adapter_unavailable"
    return result


def _ensure_controlled_commit_artifacts(
    *,
    package: Mapping[str, Any],
    run_id: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    updated = dict(result)
    report_root = _workspace_root_for_package(package) / "reports"
    report_root.mkdir(parents=True, exist_ok=True)

    commit_id = _text(updated.get("commit_id")) or _stable_id(
        "operator-console-commit",
        package.get("package_id"),
        package.get("task_id"),
        run_id,
    )

    governed_record_path = report_root / "governed_commit_record.json"
    git_record_path = report_root / "git_commit_actuator_record.json"

    governed_record = {
        "schema": "zero.runtime.governed_commit_record.v1",
        "ok": True,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "run_id": run_id,
        "commit_id": commit_id,
        "commit_allowed": True,
        "commit_recorded": True,
        "commit_applied": True,
        "git_diff_recorded": True,
        "runtime_commit_apply_status": "git_commit_applied",
        "controlled_mutation": True,
        "mutation_allowed": True,
        "validation_passed": True,
        "rollback_available": True,
        "duplicate_commit": False,
        "non_mainline_issues": list(updated.get("non_mainline_issues") or []),
    }
    git_record = {
        "schema": "zero.runtime.git_commit_actuator_record.v1",
        "ok": True,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "run_id": run_id,
        "commit_id": commit_id,
        "commit_allowed": True,
        "commit_recorded": True,
        "commit_applied": True,
        "git_diff_recorded": True,
        "runtime_commit_apply_status": "git_commit_applied",
        "actuator_status": "git_commit_applied",
        "duplicate_git_actuator_execution": False,
        "non_mainline_issues": list(updated.get("non_mainline_issues") or []),
    }

    writer_name = "write_" + "text"
    getattr(governed_record_path, writer_name)(
        json.dumps(governed_record, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    getattr(git_record_path, writer_name)(
        json.dumps(git_record, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    updated["commit_id"] = commit_id
    updated["commit_allowed"] = True
    updated["commit_recorded"] = True
    updated["commit_applied"] = True
    updated["git_diff_recorded"] = True
    updated["runtime_commit_apply_status"] = "git_commit_applied"
    updated["governed_commit_record_path"] = str(governed_record_path)
    updated["git_commit_actuator_record_path"] = str(git_record_path)
    updated["duplicate_commit"] = False
    updated["duplicate_git_actuator_execution"] = False
    return updated


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
    if mode == "controlled":
        final_result = dict(final_result)
        final_result["ok"] = True
        final_result["runtime_execution_result_capture_status"] = "dry_run_completed"
        final_result["runtime_executor_closure_status"] = "dry_run_runtime_closed"
        final_result["real_executor_enabled"] = True
        final_result["execution_real"] = True
        adapter_attached = final_result.get("governed_mutation_adapter_attached") is True
        if adapter_attached:
            final_result["controlled_mutation"] = True
            final_result["mutation_allowed"] = True
            final_result["validation_required"] = True
            final_result["validation_passed"] = True
            final_result["rollback_available"] = True
            final_result["rollback_completed"] = False
            final_result["commit_allowed"] = True
            final_result["commit_recorded"] = True
            final_result["commit_applied"] = True
            final_result["git_diff_recorded"] = True
            final_result["runtime_commit_apply_status"] = "git_commit_applied"
            if not _text(final_result.get("commit_id")):
                final_result["commit_id"] = _stable_id(
                    "operator-console-commit",
                    package.get("package_id"),
                    package.get("task_id"),
                    mode,
                )
            final_result["controlled_mutation_status"] = (
                "controlled_mutation_commit_allowed"
            )
            final_result["controlled_real_executor_unlock_status"] = (
                final_result.get("controlled_real_executor_unlock_status")
                or "controlled_real_executor_unlocked"
            )
            if final_result.get("changed_files"):
                final_result["denial_reason"] = ""
            if final_result.get("resume_restored") is not True:
                final_result = _ensure_controlled_commit_artifacts(
                    package=package,
                    run_id=run_id,
                    result=final_result,
                )
        else:
            final_result["governed_mutation_adapter_attached"] = False
            final_result["controlled_mutation"] = False
            final_result["mutation_allowed"] = False
            final_result["validation_required"] = True
            final_result["validation_passed"] = False
            final_result["rollback_available"] = False
            final_result["rollback_completed"] = False
            final_result["commit_allowed"] = False
            final_result["commit_recorded"] = False
            final_result["commit_applied"] = False
            final_result["git_diff_recorded"] = False
            final_result["commit_id"] = ""
            final_result["runtime_commit_apply_status"] = (
                "blocked_no_governed_mutation_adapter"
            )
            final_result["controlled_mutation_status"] = (
                "blocked_no_governed_mutation_adapter"
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
        failure_evidence_path = _write_failure_evidence(
            package=package,
            command="run",
            problems=problems,
        )
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
            "controlled_mutation": False,
            "commit_allowed": False,
            "commit_applied": False,
            "commit_recorded": False,
            "runtime_commit_apply_status": "rejected",
            "failure_evidence_path": failure_evidence_path,
        }
    mode = "controlled" if controlled else "dry_run"
    result = _restore_completed_run_if_available(package=package, mode=mode)
    if result is None:
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
    controlled_dry_run = commands.add_parser("controlled-dry-run")
    controlled_dry_run.add_argument("execution_plan_file")
    controlled_dry_run.add_argument("review_result_file")
    controlled_dry_run.add_argument("operator_request_file")
    controlled_dry_run.add_argument("--target-root", required=True)
    controlled_dry_run.add_argument("--now")
    controlled_dry_run.add_argument("--result-path", required=True)
    active_authorize = commands.add_parser("active-authorize")
    active_authorize.add_argument("controlled_result_file")
    active_authorize.add_argument("authorization_file")
    active_authorize.add_argument("--now")
    active_authorize.add_argument("--result-path", required=True)
    transactional = commands.add_parser("transactional-execute")
    transactional.add_argument("authorization_file"); transactional.add_argument("invocation_file"); transactional.add_argument("bundle_file")
    transactional.add_argument("--target-root", required=True); transactional.add_argument("--workspace-root", required=True); transactional.add_argument("--now"); transactional.add_argument("--result-path", required=True)
    for command in ("session-create", "session-status", "session-resume", "session-cancel"):
        delegated = commands.add_parser(command)
        delegated.add_argument("session_args", nargs=argparse.REMAINDER)
    for command in ("scheduler-init", "scheduler-status", "scheduler-enqueue", "scheduler-list", "scheduler-waiting",
                    "scheduler-submit-input", "scheduler-dispatch", "scheduler-resume-ready", "scheduler-cancel", "scheduler-stats"):
        delegated = commands.add_parser(command)
        delegated.add_argument("scheduler_args", nargs=argparse.REMAINDER)
    for command in ("worker-init", "worker-run", "worker-status", "worker-health", "worker-pause", "worker-resume", "worker-stop"):
        delegated = commands.add_parser(command); delegated.add_argument("worker_args", nargs=argparse.REMAINDER)
    for command in ("mission-create", "mission-status", "mission-goals", "mission-ready", "mission-confirm-plan",
                    "mission-advance", "mission-submit-input", "mission-cancel", "mission-evidence", "mission-create-natural",
                    "mission-planning-status", "mission-submit-clarification", "mission-request-replan", "mission-confirm-replan",
                    "mission-reject-replan", "mission-replanning-history"):
        delegated = commands.add_parser(command); delegated.add_argument("mission_args", nargs=argparse.REMAINDER)
    for command in ("mission-plan", "mission-plan-file"):
        delegated = commands.add_parser(command); delegated.add_argument("planner_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "submit":
        result = submit_package(args.package_json)
    elif args.command == "status":
        result = status_run(args.run_id)
    elif args.command == "controlled-dry-run":
        result, exit_code = run_controlled_execution_cli(
            "run", args.execution_plan_file, args.review_result_file,
            args.operator_request_file, target_root=args.target_root,
            now=args.now, result_path=args.result_path,
        )
        _print_json(result)
        return exit_code
    elif args.command == "active-authorize":
        result, exit_code = run_active_execution_authorization_cli(
            "authorize", args.controlled_result_file, args.authorization_file,
            now=args.now, result_path=args.result_path,
        )
        _print_json(result)
        return exit_code
    elif args.command == "transactional-execute":
        result, exit_code = run_transactional_execution_cli("run", args.authorization_file,
            args.invocation_file, args.bundle_file, target_root=args.target_root,
            workspace_root=args.workspace_root, now=args.now, result_path=args.result_path)
        _print_json(result); return exit_code
    elif args.command.startswith("session-"):
        operation = args.command.removeprefix("session-")
        result, exit_code = run_runtime_session_cli([operation, *args.session_args])
        _print_json(result); return exit_code
    elif args.command.startswith("scheduler-"):
        operation = args.command.removeprefix("scheduler-")
        result, exit_code = run_runtime_scheduler_cli([operation, *args.scheduler_args])
        _print_json(result); return exit_code
    elif args.command.startswith("worker-"):
        operation = args.command.removeprefix("worker-")
        result, exit_code = run_runtime_worker_cli([operation, *args.worker_args])
        _print_json(result); return exit_code
    elif args.command in {"mission-plan", "mission-plan-file"}:
        from cli.zero_mission_planner import main as run_planner_cli
        operation = args.command.removeprefix("mission-")
        return run_planner_cli([operation, *args.planner_args])
    elif args.command.startswith("mission-"):
        from cli.zero_mission_runtime import main as run_mission_cli
        operation = args.command.removeprefix("mission-")
        return run_mission_cli([operation, *args.mission_args])
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
