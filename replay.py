from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SAFETY_CLASS_BY_STEP_TYPE = {
    "read_file": "read_only",
    "workspace_read": "read_only",
    "web_search": "read_only",
    "verify": "read_only",
    "verify_file": "read_only",
    "llm": "generate_only",
    "llm_generate": "generate_only",
    "respond": "generate_only",
    "final_answer": "generate_only",
    "tool": "tool",
    "write_file": "workspace_write",
    "workspace_write": "workspace_write",
    "ensure_file": "workspace_write",
    "command": "side_effect_unknown",
    "run_python": "side_effect_unknown",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay an existing task trace in read-only mode. "
            "Do not execute the task again. Replay only summarizes existing trace/artifacts."
        )
    )
    parser.add_argument("--task", required=True, help="Task id to replay, for example task_123")
    parser.add_argument("--workspace", default="workspace", help="Workspace directory, default: workspace")
    parser.add_argument("--json", action="store_true", help="Print replay summary as JSON")
    args = parser.parse_args()

    replay = build_replay(task_id=args.task, workspace_root=Path(args.workspace))
    if args.json:
        print(json.dumps(replay, ensure_ascii=False, indent=2))
    else:
        print(format_replay(replay))
    return 0 if replay.get("ok") else 1


def build_replay(*, task_id: str, workspace_root: Path) -> Dict[str, Any]:
    task_id = str(task_id or "").strip()
    workspace_root = workspace_root.resolve(strict=False)
    task_dir = (workspace_root / "tasks" / task_id).resolve(strict=False)

    if not task_id:
        return _error_replay(task_id="", task_dir=task_dir, error="task id is required")
    if not _is_relative_to(task_dir, workspace_root):
        return _error_replay(task_id=task_id, task_dir=task_dir, error="task path escapes workspace")
    if not task_dir.exists() or not task_dir.is_dir():
        return _error_replay(task_id=task_id, task_dir=task_dir, error=f"task not found: {task_id}")

    plan = _read_json(task_dir / "plan.json", default={})
    runtime_state = _read_json(task_dir / "runtime_state.json", default={})
    result = _read_json(task_dir / "result.json", default={})
    execution_log = _read_json(task_dir / "execution_log.json", default=[])
    trace = _read_json(task_dir / "trace.json", default={})

    task_summary = _summarize_task(
        task_id=task_id,
        task_dir=task_dir,
        plan=plan,
        runtime_state=runtime_state,
        result=result,
    )
    pipeline_payload = _find_git_pipeline_payload(result, runtime_state, execution_log, trace)
    if pipeline_payload:
        steps = _git_pipeline_steps(pipeline_payload)
    else:
        steps = _generic_steps(plan=plan, runtime_state=runtime_state, execution_log=execution_log, result=result)

    artifacts = _collect_artifacts(
        workspace_root=workspace_root,
        task_dir=task_dir,
        payloads=[pipeline_payload, result, runtime_state, trace],
    )
    safety = _collect_safety_flags([pipeline_payload, result, runtime_state, execution_log, trace])
    summary = _build_one_line_summary(steps=steps, safety=safety)

    return {
        "ok": True,
        "replay_mode": "read_only",
        "task": task_summary,
        "steps": steps,
        "artifacts": artifacts,
        "safety": safety,
        "summary": summary,
        "sources": {
            "plan": str(task_dir / "plan.json"),
            "runtime_state": str(task_dir / "runtime_state.json"),
            "result": str(task_dir / "result.json"),
            "execution_log": str(task_dir / "execution_log.json"),
            "trace": str(task_dir / "trace.json"),
        },
    }


def format_replay(replay: Dict[str, Any]) -> str:
    if not replay.get("ok"):
        lines = [
            "Trace Replay",
            "Mode: read_only",
            f"Error: {replay.get('error')}",
        ]
        return "\n".join(lines)

    task = replay.get("task", {}) if isinstance(replay.get("task"), dict) else {}
    safety = replay.get("safety", {}) if isinstance(replay.get("safety"), dict) else {}
    artifacts = replay.get("artifacts", []) if isinstance(replay.get("artifacts"), list) else []
    steps = replay.get("steps", []) if isinstance(replay.get("steps"), list) else []

    lines = [
        "Trace Replay",
        "Mode: read_only",
        "Note: replay only summarizes existing trace/artifacts; it does not execute tasks or tools.",
        "",
        f"Task: {task.get('task_id') or ''}",
        f"Status: {task.get('status') or 'unknown'}",
    ]
    goal = str(task.get("goal") or "").strip()
    if goal:
        lines.append(f"Goal: {goal}")

    lines.extend(["", "Steps:"])
    if steps:
        for index, step in enumerate(steps, start=1):
            lines.append(
                f"{index}. {step.get('name') or 'unknown':<18} "
                f"{step.get('status') or 'unknown':<7} "
                f"{step.get('safety_class') or 'unknown':<16} "
                f"(origin: {step.get('origin') or 'unknown'})"
            )
    else:
        lines.append("- no step data found")

    lines.extend(["", "Artifacts:"])
    if artifacts:
        for item in artifacts:
            path = item.get("name") or item.get("logical_path") or item.get("path") or ""
            exists = "exists" if item.get("exists") else "missing"
            size_text = f"{item.get('size_bytes')}B" if item.get("size_bytes") is not None else "unknown size"
            hash_text = f", sha256:{item.get('sha256_12')}" if item.get("sha256_12") else ""
            lines.append(f"- {path} (size: {size_text}{hash_text}, {exists})")
    else:
        lines.append("- none found")

    lines.extend(
        [
            "",
            "Safety:",
            f"- git_commit: {_bool_text(safety.get('git_commit'))}",
            f"- git_push: {_bool_text(safety.get('git_push'))}",
            f"- github_create_pr: {_bool_text(safety.get('github_create_pr'))}",
            f"- mutation_attempt: {int(safety.get('mutation_attempt') or 0)}",
            f"- no_commit_push_pr: {_bool_text(safety.get('no_commit_push_pr'))}",
            "- replay_mode: read_only",
        ]
    )
    summary = str(replay.get("summary") or "").strip()
    if summary:
        lines.extend(["", f"Summary: {summary}"])
    return "\n".join(lines)


def _summarize_task(
    *,
    task_id: str,
    task_dir: Path,
    plan: Any,
    runtime_state: Any,
    result: Any,
) -> Dict[str, Any]:
    status = _first_nonempty(
        _dict_get(result, "status"),
        _dict_get(runtime_state, "status"),
        "unknown",
    )
    goal = _first_nonempty(
        _dict_get(runtime_state, "goal"),
        _dict_get(result, "goal"),
        _dict_get(plan, "goal"),
        "",
    )
    return {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "status": str(status or "unknown"),
        "goal": str(goal or ""),
    }


def _git_pipeline_steps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    commit_result = payload.get("commit_message") if isinstance(payload.get("commit_message"), dict) else {}
    pr_result = payload.get("pr_description") if isinstance(payload.get("pr_description"), dict) else {}
    commit_outbox = commit_result.get("outbox_result") if isinstance(commit_result.get("outbox_result"), dict) else {}
    pr_outbox = pr_result.get("outbox_result") if isinstance(pr_result.get("outbox_result"), dict) else {}
    outbox_ok = bool(commit_outbox.get("ok") or pr_outbox.get("ok"))

    return [
        _step("git_diff", _status(payload.get("diff_result")), "read_only", "git"),
        _step("git_status", _status(payload.get("status_result")), "read_only", "git"),
        _step("analyze", "ok" if isinstance(payload.get("analysis"), dict) else "unknown", "generate_only", "system"),
        _step("generate_commit", _status(commit_result), "generate_only", _origin_from_payload(commit_result, "llm")),
        _step("generate_pr", _status(pr_result), "generate_only", _origin_from_payload(pr_result, "llm")),
        _step("outbox_write", "ok" if outbox_ok else "unknown", "workspace_write", "github_outbox"),
    ]


def _generic_steps(*, plan: Any, runtime_state: Any, execution_log: Any, result: Any) -> List[Dict[str, Any]]:
    steps = _extract_steps(runtime_state) or _extract_steps(plan) or _extract_steps(result)
    results = _extract_results(runtime_state) or _extract_results(result)

    summarized: List[Dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        step_type = str(_dict_get(step, "type") or "unknown").strip().lower()
        name = _step_name(step)
        status = _result_status_at(results, index - 1)
        summarized.append(
            _step(
                name=name,
                status=status,
                safety_class=_safety_class_for_step(step),
                origin=_origin_for_step(step),
            )
        )

    if summarized:
        return summarized

    if isinstance(execution_log, list):
        for item in execution_log:
            if not isinstance(item, dict):
                continue
            name = str(item.get("step_type") or item.get("type") or item.get("title") or "execution").strip()
            summarized.append(
                _step(
                    name=name,
                    status=_status(item),
                    safety_class=SAFETY_CLASS_BY_STEP_TYPE.get(name.lower(), "unknown"),
                    origin=_origin_from_payload(item, "execution_log"),
                )
            )

    return summarized


def _find_git_pipeline_payload(*payloads: Any) -> Optional[Dict[str, Any]]:
    for payload in payloads:
        found = _find_dict(payload, lambda item: item.get("tool") == "git_pipeline" and "analysis" in item)
        if found:
            return found
        found = _find_dict(payload, lambda item: item.get("tool") == "git_pipeline" and isinstance(item.get("output"), dict))
        if found and isinstance(found.get("output"), dict):
            output = found["output"]
            if output.get("tool") == "git_pipeline" or "analysis" in output:
                return output
    return None


def _collect_artifacts(*, workspace_root: Path, task_dir: Path, payloads: Iterable[Any]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    items: List[Dict[str, Any]] = []

    for payload in payloads:
        if not payload:
            continue
        for path_text in _walk_artifact_paths(payload):
            artifact = _artifact_record(path_text, workspace_root=workspace_root, task_dir=task_dir)
            key = artifact.get("path", "")
            if key and key not in seen:
                seen.add(key)
                items.append(artifact)

    return items


def _walk_artifact_paths(payload: Any) -> Iterable[str]:
    if isinstance(payload, dict):
        artifacts = payload.get("artifacts")
        if isinstance(artifacts, dict):
            for value in artifacts.values():
                if isinstance(value, str) and value.strip():
                    yield value
        if isinstance(artifacts, list):
            for item in artifacts:
                if isinstance(item, dict):
                    value = item.get("logical_path") or item.get("path") or item.get("full_path")
                    if isinstance(value, str) and value.strip():
                        yield value

        for key in ("output_path", "result_path", "plan_file", "runtime_state_file", "execution_log_file", "trace_file"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                yield value

        for value in payload.values():
            yield from _walk_artifact_paths(value)

    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_artifact_paths(item)


def _artifact_record(path_text: str, *, workspace_root: Path, task_dir: Path) -> Dict[str, Any]:
    raw = Path(str(path_text).strip())
    if not raw.is_absolute():
        root_parent = workspace_root.parent
        candidate = (root_parent / raw).resolve(strict=False)
        if not _is_relative_to(candidate, root_parent):
            candidate = (task_dir / raw).resolve(strict=False)
    else:
        candidate = raw.resolve(strict=False)

    logical = _logical_path(candidate, workspace_root=workspace_root)
    size_bytes = candidate.stat().st_size if candidate.exists() and candidate.is_file() else None
    return {
        "path": str(candidate),
        "name": candidate.name,
        "logical_path": logical,
        "exists": candidate.exists(),
        "size_bytes": size_bytes,
        "sha256_12": _sha256_12(candidate) if candidate.exists() and candidate.is_file() else "",
    }


def _collect_safety_flags(payloads: Iterable[Any]) -> Dict[str, Any]:
    flags = {
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
    for payload in payloads:
        for key in list(flags.keys()):
            value = _find_first_key(payload, key)
            if isinstance(value, bool):
                flags[key] = flags[key] or value
    flags["mutation_attempt"] = sum(1 for value in flags.values() if value is True)
    flags["no_commit_push_pr"] = not (flags["git_commit"] or flags["git_push"] or flags["github_create_pr"])
    return flags


def _extract_steps(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        steps = payload.get("steps")
        if isinstance(steps, list):
            return [item for item in steps if isinstance(item, dict)]
        planner_result = payload.get("planner_result")
        if isinstance(planner_result, dict):
            return _extract_steps(planner_result)
    return []


def _extract_results(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("results", "step_results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _step_name(step: Any) -> str:
    if not isinstance(step, dict):
        return "unknown"
    step_type = str(step.get("type") or "unknown").strip()
    if step_type == "tool":
        return str(step.get("tool_name") or step.get("tool") or "tool").strip()
    if step_type in {"llm", "llm_generate"} and step.get("mode"):
        return str(step.get("mode")).strip()
    return step_type


def _safety_class_for_step(step: Any) -> str:
    if not isinstance(step, dict):
        return "unknown"
    step_type = str(step.get("type") or "").strip().lower()
    if step_type == "tool":
        tool_name = str(step.get("tool_name") or step.get("tool") or "").strip().lower()
        if tool_name == "git_pipeline":
            return "pipeline"
    return SAFETY_CLASS_BY_STEP_TYPE.get(step_type, "unknown")


def _origin_for_step(step: Any) -> str:
    if not isinstance(step, dict):
        return "unknown"
    origin = str(step.get("origin") or "").strip()
    if origin:
        return origin
    step_type = str(step.get("type") or "").strip().lower()
    if step_type == "tool":
        tool_name = str(step.get("tool_name") or step.get("tool") or "").strip()
        return tool_name or "tool"
    if step_type in {"read_file", "workspace_read", "verify", "verify_file"}:
        return "filesystem"
    if step_type in {"llm", "llm_generate"}:
        return "llm"
    if step_type in {"write_file", "workspace_write", "ensure_file"}:
        return "workspace"
    if step_type in {"command", "run_python"}:
        return "local_command"
    return "planner"


def _origin_from_payload(payload: Any, fallback: str) -> str:
    origin = _find_first_key(payload, "origin")
    if isinstance(origin, str) and origin.strip():
        return origin.strip()
    tool = _find_first_key(payload, "tool")
    if isinstance(tool, str) and tool.strip():
        return tool.strip()
    return fallback


def _result_status_at(results: List[Dict[str, Any]], index: int) -> str:
    if index < 0 or index >= len(results):
        return "unknown"
    return _status(results[index])


def _status(payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("ok") is True:
            return "ok"
        if payload.get("ok") is False:
            return "failed"
        status = str(payload.get("status") or "").strip()
        if status:
            if status.lower() in {"success", "finished", "completed", "done"}:
                return "ok"
            return status
    return "unknown"


def _step(name: str, status: str, safety_class: str, origin: str) -> Dict[str, Any]:
    return {
        "name": str(name or "unknown"),
        "status": str(status or "unknown"),
        "safety_class": str(safety_class or "unknown"),
        "origin": str(origin or "unknown"),
    }


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists() or not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _dict_get(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _find_dict(payload: Any, predicate) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        if predicate(payload):
            return payload
        for value in payload.values():
            found = _find_dict(value, predicate)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_dict(item, predicate)
            if found:
                return found
    return None


def _find_first_key(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        for value in payload.values():
            found = _find_first_key(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_first_key(item, key)
            if found is not None:
                return found
    return None


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _logical_path(path: Path, *, workspace_root: Path) -> str:
    repo_root = workspace_root.parent.resolve(strict=False)
    try:
        return path.resolve(strict=False).relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _sha256_12(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _build_one_line_summary(*, steps: List[Dict[str, Any]], safety: Dict[str, Any]) -> str:
    has_git_read = any(step.get("origin") == "git" for step in steps)
    has_generated = any(step.get("safety_class") == "generate_only" for step in steps)
    has_outbox = any(step.get("name") == "outbox_write" for step in steps)
    if has_git_read and has_generated and has_outbox and safety.get("no_commit_push_pr"):
        return "ZERO replayed a read-only git analysis pipeline that generated artifacts without mutating the repository."
    if safety.get("no_commit_push_pr"):
        return "ZERO replayed existing artifacts without mutating the repository."
    return "ZERO replay found mutation flags in the existing trace; review before proceeding."


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
        return True
    except ValueError:
        return False


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _error_replay(*, task_id: str, task_dir: Path, error: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "replay_mode": "read_only",
        "task": {
            "task_id": task_id,
            "task_dir": str(task_dir),
            "status": "unknown",
        },
        "steps": [],
        "artifacts": [],
        "safety": {
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
            "no_commit_push_pr": True,
        },
        "error": error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
