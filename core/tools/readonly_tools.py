from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from core.tools.tool_policy import build_tool_trace_event, evaluate_tool_policy


DEFAULT_GIT_TIMEOUT_SECONDS = 5
DEFAULT_DIFF_MAX_LINES = 800
SENSITIVE_READ_PATTERNS = (
    ".env",
    ".env.*",
    ".git/*",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    "*.key",
)


def git_status(*, repo_root: Any = ".", task_id: str = "", trace_id: str = "") -> Dict[str, Any]:
    return _run_git_readonly(
        ["git", "status", "--short"],
        repo_root=repo_root,
        tool_name="git_status",
        input_summary="git status --short",
        task_id=task_id,
        trace_id=trace_id,
        timeout_seconds=DEFAULT_GIT_TIMEOUT_SECONDS,
    )


def git_diff(
    *,
    repo_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
    max_lines: int = DEFAULT_DIFF_MAX_LINES,
) -> Dict[str, Any]:
    return _run_git_readonly(
        ["git", "diff", "--", "."],
        repo_root=repo_root,
        tool_name="git_diff",
        input_summary="git diff -- .",
        task_id=task_id,
        trace_id=trace_id,
        timeout_seconds=DEFAULT_GIT_TIMEOUT_SECONDS,
        max_lines=max_lines,
    )


def file_reader(
    path: str,
    *,
    repo_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    root = Path(repo_root).resolve(strict=False)
    target = Path(str(path or "").strip())
    if not target.is_absolute():
        target = root / target
    target = target.resolve(strict=False)

    policy_decision = evaluate_tool_policy(
        tool_class="read_only",
        actual_side_effect_level="read_only",
        workspace_root=root,
    )

    try:
        target.relative_to(root)
    except ValueError:
        return _readonly_result(
            ok=False,
            tool_name="file_reader",
            input_summary=f"read file: {path}",
            output_summary="",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error="path_escapes_repo_root",
        )

    relative_path = target.relative_to(root).as_posix()
    if _is_sensitive_read_path(relative_path):
        return _readonly_result(
            ok=False,
            tool_name="file_reader",
            input_summary=f"read file: {path}",
            output_summary="",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error="sensitive_path_denied",
        )

    if not target.is_file():
        return _readonly_result(
            ok=False,
            tool_name="file_reader",
            input_summary=f"read file: {path}",
            output_summary="",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error="file_not_found",
        )

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        return _readonly_result(
            ok=False,
            tool_name="file_reader",
            input_summary=f"read file: {path}",
            output_summary="",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error=str(exc),
        )

    result = _readonly_result(
        ok=True,
        tool_name="file_reader",
        input_summary=f"read file: {path}",
        output_summary=f"{len(content)} chars",
        policy_decision=policy_decision,
        task_id=task_id,
        trace_id=trace_id,
    )
    result.update(
        {
            "path": str(target),
            "content": content,
        }
    )
    return result


def _run_git_readonly(
    command: List[str],
    *,
    repo_root: Any,
    tool_name: str,
    input_summary: str,
    task_id: str,
    trace_id: str,
    timeout_seconds: int,
    max_lines: int | None = None,
) -> Dict[str, Any]:
    root = Path(repo_root).resolve(strict=False)
    policy_decision = evaluate_tool_policy(
        tool_class="read_only",
        actual_side_effect_level="read_only",
        workspace_root=root,
    )

    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        result = _readonly_result(
            ok=False,
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=f"{len(stdout)} chars stdout before timeout",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error=f"git read-only command timed out after {timeout_seconds}s",
        )
        result.update(
            {
                "command": command,
                "cwd": str(root),
                "returncode": None,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": True,
                "truncated": False,
            }
        )
        return result
    except Exception as exc:
        return _readonly_result(
            ok=False,
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary="",
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error=str(exc),
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    stdout, truncated, original_line_count = _truncate_lines(stdout, max_lines=max_lines)
    ok = completed.returncode == 0
    result = _readonly_result(
        ok=ok,
        tool_name=tool_name,
        input_summary=input_summary,
        output_summary=f"{len(stdout)} chars stdout",
        policy_decision=policy_decision,
        task_id=task_id,
        trace_id=trace_id,
        error="" if ok else stderr.strip() or f"git exited {completed.returncode}",
    )
    result.update(
        {
            "command": command,
            "cwd": str(root),
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": False,
            "truncated": truncated,
            "original_line_count": original_line_count,
            "max_lines": max_lines,
        }
    )
    return result


def _readonly_result(
    *,
    ok: bool,
    tool_name: str,
    input_summary: str,
    output_summary: str,
    policy_decision: Dict[str, Any],
    task_id: str,
    trace_id: str,
    error: str = "",
) -> Dict[str, Any]:
    trace = build_tool_trace_event(
        trace_id=trace_id,
        task_id=task_id,
        tool_name=tool_name,
        tool_class="read_only",
        input_summary=input_summary,
        output_summary=output_summary,
        side_effect_level="read_only",
        policy_decision=policy_decision,
        executor_approved=False,
        status="success" if ok else "error",
        error=error,
        tool_input_full={"command_or_path": input_summary},
    )
    return {
        "ok": bool(ok),
        "tool": tool_name,
        "tool_class": "read_only",
        "side_effect_level": "read_only",
        "summary": output_summary,
        "error": None if ok else error,
        "trace": trace,
        "changed_files": [],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def _truncate_lines(text: str, *, max_lines: int | None) -> tuple[str, bool, int]:
    lines = str(text or "").splitlines()
    original_line_count = len(lines)
    if max_lines is None or max_lines <= 0 or original_line_count <= max_lines:
        return text, False, original_line_count

    kept = lines[:max_lines]
    kept.append(f"... [truncated {original_line_count - max_lines} lines]")
    return "\n".join(kept) + "\n", True, original_line_count


def _is_sensitive_read_path(relative_path: str) -> bool:
    import fnmatch

    normalized = str(relative_path or "").replace("\\", "/").lstrip("/")
    if normalized == ".git" or normalized.startswith(".git/"):
        return True
    for pattern in SENSITIVE_READ_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(Path(normalized).name, pattern):
            return True
    return False
