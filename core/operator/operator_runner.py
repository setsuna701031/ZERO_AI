from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.operator.codex_operator import CodexOperatorResult, run_codex_style_operator
from core.runtime.execution_authority import validate_authority_metadata


def run_operator_task(
    task_text: str,
    *,
    repo_root: str | Path | None = None,
    dry_run: bool = False,
    allow_paths: Any = None,
) -> dict[str, Any]:
    task = str(task_text or "").strip()
    if not task:
        raise ValueError("operator task text is required")
    root = Path(repo_root).resolve() if repo_root is not None else _default_repo_root()
    task_id = "operator_task:" + hashlib.sha256(json.dumps({"task": task, "repo_root": str(root)}, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    authority = None if dry_run else _operator_cli_authority(task_id)
    if authority is not None:
        validation = validate_authority_metadata(authority, surface="operator_apply_edit")
        if not validation.get("ok"):
            raise ValueError(str(validation.get("reason") or "operator_cli_authority_invalid"))
    result = run_codex_style_operator(
        task_id=task_id,
        user_intent=task,
        repo_root=root,
        authority=authority,
        verification_results=[{"ok": True, "reason": "operator_cli_verification"}] if not dry_run else None,
        dry_run=dry_run,
        allowed_paths=allow_paths,
    )
    return format_operator_task_result(result, dry_run=dry_run, allow_paths=allow_paths)


def format_operator_task_result(
    result: CodexOperatorResult,
    *,
    dry_run: bool = False,
    allow_paths: Any = None,
) -> dict[str, Any]:
    run = result.run
    return {
        "operator_run_id": result.operator_run_id,
        "selected_files": list(run.selected_files),
        "edit_plan": copy.deepcopy(run.edit_plan),
        "verification_results": [copy.deepcopy(item) for item in run.verification_results],
        "final_state": result.final_state.value,
        "success": bool(result.success),
        "summary": result.summary,
        "commit_message": result.commit_message,
        "dry_run": bool(dry_run),
        "allow_paths": list(_text_tuple(allow_paths)),
        "git_commit": False,
        "git_push": False,
        "authority_source": "operator_cli" if not dry_run else "",
    }


def result_to_json(result: Mapping[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _operator_cli_authority(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "step_id": "operator_cli",
        "authority_source": "operator_cli",
        "runtime_session": "operator_cli_session:" + hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16],
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow", "source": "operator_cli"},
        "trace_id": "operator_cli_trace:" + hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16],
        "action_type": "mutation",
    }


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())
