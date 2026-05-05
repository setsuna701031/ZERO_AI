"""
self_edit_loop.py

ZERO Self-Edit Loop v5.6.4

Purpose:
- Run conservative controlled self-edits for explicit replacement tasks:
      Modify path/to/file.py: replace 'old' with 'new'
- Support:
    - single-line safe replacement;
    - multi-line block replacement;
    - indentation preservation;
    - verification command allowlist;
    - simple indentation repair after verify failure;
    - Python AST safety checks for .py files.

v5.6.4:
- Fixes function index discovery with a more robust os.walk-based scanner.
- Adds a direct workspace/shared/sample_code.py fallback candidate when present.
- Adds function scan diagnostics to LLM plan metadata.
- Keeps validation that LLM-planned function targets must exist in the selected Python file.
- Preferred local usage:
      --planner llm --ollama-model qwen2.5:7b
- LLM Planner remains OFF by default.
- Every LLM-generated step is validated through the same controlled edit parser.
- Invalid / non-controlled / unsafe planner output is rejected before execution.
- Does not allow arbitrary patching.
- Does not let the LLM write files directly.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import subprocess
import time
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_REPO_ROOT = "."
DEFAULT_VERIFY_TIMEOUT_SECONDS = 60
DEFAULT_MAX_CHANGED_LINES = 40
DEFAULT_MAX_INSERTED_LINES = 30
DEFAULT_MAX_REMOVED_LINES = 30
DEFAULT_LLM_PLANNER_TIMEOUT_SECONDS = 60
DEFAULT_MAX_PLANNER_STEPS = 8
DEFAULT_LLM_PLANNER_RETRIES = 1
DEFAULT_MAX_WORKSPACE_FILES_FOR_PROMPT = 80
CODE_CHAIN_VERSION = "self_edit_loop_v5_6_4"


BLOCKED_STATUSES = {"blocked", "failed", "error", "rejected", "denied", "rolled_back"}
OK_STATUSES = {"ok", "success", "done", "finished", "applied", "ready"}

SAFE_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
}


@dataclass
class VerifyResult:
    command: str
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


@dataclass
class SelfEditAttempt:
    attempt: int
    task: str
    edit_result: dict[str, Any]
    verify_results: list[VerifyResult] = field(default_factory=list)
    correction: dict[str, Any] = field(default_factory=dict)
    ok: bool = False
    reason: str = ""


@dataclass
class SelfEditLoopResult:
    ok: bool
    status: str
    task: str
    attempts: list[SelfEditAttempt]
    max_attempts: int
    repo_root: str
    final_task: str
    final_reason: str = ""
    code_chain_version: str = CODE_CHAIN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "task": self.task,
            "final_task": self.final_task,
            "max_attempts": self.max_attempts,
            "repo_root": self.repo_root,
            "final_reason": self.final_reason,
            "code_chain_version": self.code_chain_version,
            "attempts": [
                {
                    "attempt": item.attempt,
                    "task": item.task,
                    "edit_result": item.edit_result,
                    "verify_results": [asdict(v) for v in item.verify_results],
                    "correction": item.correction,
                    "ok": item.ok,
                    "reason": item.reason,
                }
                for item in self.attempts
            ],
        }


@dataclass
class TextFileSnapshot:
    path: Path
    content: str
    encoding: str
    had_bom: bool
    newline: str
    had_final_newline: bool


@dataclass
class TransactionSnapshot:
    path: Path
    content: str
    had_bom: bool


class SelfEditSafetyError(RuntimeError):
    """Raised when a self-edit request violates local safety boundaries."""


def _load_repo_edit_bridge() -> Any:
    from core.tools.repo_edit_agent_bridge import run_repo_edit_decision

    return run_repo_edit_decision


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_path_text(path: str) -> str:
    text = str(path or "").strip().strip("'\"`")
    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.lstrip("./")


def _contains_core_path(task: str) -> bool:
    text = task.replace("\\", "/")
    markers = (
        " core/",
        "core/",
        " app.py",
        "app.py",
        " services/",
        "services/",
        " tests/",
        "tests/",
        " ui/",
        "ui/",
    )
    return any(marker in text for marker in markers)


def _contains_workspace_path(task: str) -> bool:
    return "workspace/" in task.replace("\\", "/")


def _looks_like_edit_task(task: str) -> bool:
    text = task.lower()
    return (
        "replace" in text
        and " with " in text
        and (".py" in text or ".md" in text or ".txt" in text or ".json" in text)
    )


def validate_self_edit_task(task: str, *, allow_core: bool = False) -> None:
    task = _normalize_text(task)
    if not task:
        raise SelfEditSafetyError("task is empty")

    if not _looks_like_edit_task(task):
        raise SelfEditSafetyError(
            "task must be an explicit controlled replacement instruction, e.g. "
            "Modify workspace/shared/file.py: replace 'old' with 'new'"
        )

    if not allow_core and _contains_core_path(task):
        raise SelfEditSafetyError(
            "core/app/services/tests/ui edits are blocked by default; pass --allow-core only after confirming the task"
        )

    if not allow_core and not _contains_workspace_path(task):
        raise SelfEditSafetyError("non-core safe mode requires workspace/... target paths")

    forbidden_words = (
        "delete ",
        "remove file",
        "rm ",
        "rmdir",
        "del ",
        "erase ",
        "format ",
        "rename ",
        "move ",
        "mv ",
        "chmod ",
        "chown ",
        "curl ",
        "wget ",
        "powershell ",
        "cmd.exe",
        "bash ",
    )
    lowered = task.lower()
    for word in forbidden_words:
        if word in lowered:
            raise SelfEditSafetyError(f"forbidden operation in self-edit task: {word.strip()}")


def _split_command(command: str) -> list[str]:
    command = _normalize_text(command)
    if not command:
        return []

    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def _verify_command_allowed(command: str) -> bool:
    text = _normalize_text(command)
    if not text:
        return False

    lowered = text.lower().strip()

    allowed_prefixes = (
        "python -m py_compile ",
        "py -m py_compile ",
        "python -m pytest ",
        "pytest ",
    )
    if not any(lowered.startswith(prefix) for prefix in allowed_prefixes):
        return False

    blocked_fragments = (
        "&&",
        "||",
        ";",
        "|",
        ">",
        "<",
        "`",
        "$(",
        "rm ",
        "del ",
        "erase ",
        "format ",
        "curl ",
        "wget ",
        "powershell",
        "cmd.exe",
        "bash",
    )
    return not any(fragment in lowered for fragment in blocked_fragments)


def run_verify_command(
    command: str,
    *,
    repo_root: str | Path = ".",
    timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
) -> VerifyResult:
    command = _normalize_text(command)
    started = time.time()

    if not _verify_command_allowed(command):
        return VerifyResult(
            command=command,
            ok=False,
            returncode=-1,
            stdout="",
            stderr="verification command blocked by self_edit_loop allowlist",
            elapsed_seconds=0.0,
        )

    args = _split_command(command)
    if not args:
        return VerifyResult(
            command=command,
            ok=False,
            returncode=-1,
            stdout="",
            stderr="empty verification command",
            elapsed_seconds=0.0,
        )

    try:
        completed = subprocess.run(
            args,
            cwd=str(Path(repo_root).resolve()),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
        )
        elapsed = time.time() - started
        return VerifyResult(
            command=command,
            ok=completed.returncode == 0,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_seconds=elapsed,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - started
        return VerifyResult(
            command=command,
            ok=False,
            returncode=-1,
            stdout=exc.stdout or "",
            stderr=f"verification timed out after {timeout_seconds}s",
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        elapsed = time.time() - started
        return VerifyResult(
            command=command,
            ok=False,
            returncode=-1,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=elapsed,
        )


def _edit_result_status(edit_result: dict[str, Any]) -> str:
    if not isinstance(edit_result, dict):
        return ""
    return str(edit_result.get("status") or "").strip().lower()


def _edit_result_ok(edit_result: dict[str, Any]) -> bool:
    if not isinstance(edit_result, dict):
        return False

    status = _edit_result_status(edit_result)
    if status in BLOCKED_STATUSES:
        return False

    if edit_result.get("multi_edit") is True:
        transaction = edit_result.get("transaction")
        if isinstance(transaction, dict) and transaction.get("rolled_back") is True:
            return False

    tool_result = edit_result.get("tool_result")
    if isinstance(tool_result, dict):
        tool_status = str(tool_result.get("status") or "").strip().lower()
        if tool_status in BLOCKED_STATUSES:
            return False
        if tool_result.get("applied_to_workspace") is False:
            return False
        if tool_result.get("ok") is True:
            return True
        if tool_status in OK_STATUSES:
            return True

    return status in OK_STATUSES


def _extract_nested_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_extract_nested_dicts(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_nested_dicts(item))
    return found


def _extract_error_text(edit_result: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in _extract_nested_dicts(edit_result):
        for key in ("error", "reason", "report", "final_answer", "message", "status"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                pieces.append(value.strip())
    return "\n".join(pieces)


def _is_old_text_mismatch(edit_result: dict[str, Any]) -> bool:
    text = _extract_error_text(edit_result).lower()
    markers = (
        "old_text was not found",
        "old text was not found",
        "refusing blind edit",
        "controlled_replace requires",
        "old_text not found",
    )
    return any(marker in text for marker in markers)


def _shell_quote_single(text: str) -> str:
    return "'" + str(text).replace("'", "\\'") + "'"


def _shell_unquote_single(text: str) -> str:
    return str(text).replace("\\'", "'")


def _decode_task_literal(text: str) -> str:
    value = str(text or "")
    value = value.replace("\\r\\n", "\n")
    value = value.replace("\\n", "\n")
    value = value.replace("\\t", "\t")
    return value


def _make_replace_task(file_path: str, old_text: str, new_text: str) -> str:
    return (
        f"Modify {file_path}: replace "
        f"{_shell_quote_single(old_text)} with {_shell_quote_single(new_text)}"
    )


def _parse_simple_replace_task(task: str) -> dict[str, str]:
    """
    Parse supported task forms:

        Modify path/to/file.py: replace 'old' with 'new'
        Modify function add in path/to/file.py: replace 'old' with 'new'
        Modify path/to/file.py function add: replace 'old' with 'new'
        Modify path/to/file.py: in function add replace 'old' with 'new'

    Supports escaped apostrophes and literal \\n in old/new text.
    """
    text = _normalize_text(task)

    patterns = [
        (
            "function_first",
            r"^Modify\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+?):\s*replace\s+'((?:\\'|[^'])*)'\s+with\s+'((?:\\'|[^'])*)'\s*$",
        ),
        (
            "path_then_function",
            r"^Modify\s+(.+?)\s+function\s+([A-Za-z_][A-Za-z0-9_]*):\s*replace\s+'((?:\\'|[^'])*)'\s+with\s+'((?:\\'|[^'])*)'\s*$",
        ),
        (
            "path_colon_in_function",
            r"^Modify\s+(.+?):\s*in\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s+replace\s+'((?:\\'|[^'])*)'\s+with\s+'((?:\\'|[^'])*)'\s*$",
        ),
        (
            "plain",
            r"^Modify\s+(.+?):\s*replace\s+'((?:\\'|[^'])*)'\s+with\s+'((?:\\'|[^'])*)'\s*$",
        ),
    ]

    for mode, pattern in patterns:
        match = re.match(pattern, text, flags=re.DOTALL)
        if not match:
            continue

        if mode == "function_first":
            function_name = match.group(1)
            file_path = match.group(2)
            old_text = match.group(3)
            new_text = match.group(4)
        elif mode in {"path_then_function", "path_colon_in_function"}:
            file_path = match.group(1)
            function_name = match.group(2)
            old_text = match.group(3)
            new_text = match.group(4)
        else:
            file_path = match.group(1)
            function_name = ""
            old_text = match.group(2)
            new_text = match.group(3)

        return {
            "file_path": _normalize_path_text(file_path),
            "function_name": function_name,
            "old_text": _decode_task_literal(_shell_unquote_single(old_text)),
            "new_text": _decode_task_literal(_shell_unquote_single(new_text)),
            "parse_mode": mode,
        }

    return {}


def _leading_ws(text: str) -> str:
    value = str(text or "")
    return value[: len(value) - len(value.lstrip(" \t"))]


def _is_safe_target_path(file_path: str, *, allow_core: bool) -> bool:
    normalized = _normalize_path_text(file_path)
    if not normalized:
        return False

    lowered = normalized.lower()
    if ".." in normalized.split("/"):
        return False

    suffix = Path(lowered).suffix
    if suffix not in SAFE_TEXT_SUFFIXES:
        return False

    if allow_core:
        return True

    return lowered.startswith("workspace/")


def _resolve_target_path(file_path: str, *, repo_root: str | Path, allow_core: bool) -> Path:
    normalized = _normalize_path_text(file_path)
    if not _is_safe_target_path(normalized, allow_core=allow_core):
        raise SelfEditSafetyError(f"unsafe target path for direct replace: {file_path}")

    root = Path(repo_root).resolve()
    target = (root / normalized).resolve()

    if not str(target).startswith(str(root)):
        raise SelfEditSafetyError(f"target path escapes repo root: {file_path}")

    return target


def _decode_text_bytes(raw: bytes) -> tuple[str, str, bool]:
    """
    Decode text file bytes safely.

    v2.2 rule:
    - UTF-8 BOM is accepted and stripped from returned content.
    - Files are primarily treated as UTF-8.
    - Fallback to utf-8-sig for defensive compatibility.
    """
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]

    try:
        return raw.decode("utf-8"), "utf-8", had_bom
    except UnicodeDecodeError:
        return raw.decode("utf-8-sig"), "utf-8-sig", had_bom


def _line_ending_of(content: str) -> str:
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def _split_keep_style(content: str) -> tuple[list[str], str, bool]:
    newline = _line_ending_of(content)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    had_final_newline = normalized.endswith("\n")
    lines = normalized.split("\n")
    if had_final_newline:
        lines = lines[:-1]
    return lines, newline, had_final_newline


def _join_keep_style(lines: list[str], newline: str, had_final_newline: bool) -> str:
    content = newline.join(lines)
    if had_final_newline:
        content += newline
    return content


def _read_text_snapshot(path: Path) -> TextFileSnapshot:
    raw = path.read_bytes()
    content, encoding, had_bom = _decode_text_bytes(raw)

    # Defensive cleanup: if a BOM reached the decoded string anyway, remove it.
    if content.startswith("\ufeff"):
        content = content.lstrip("\ufeff")
        had_bom = True

    lines, newline, had_final_newline = _split_keep_style(content)
    normalized_content = _join_keep_style(lines, newline, had_final_newline)

    return TextFileSnapshot(
        path=path,
        content=normalized_content,
        encoding=encoding,
        had_bom=had_bom,
        newline=newline,
        had_final_newline=had_final_newline,
    )


def _read_text_file(path: Path) -> str:
    return _read_text_snapshot(path).content


def _write_text_file(path: Path, content: str, *, keep_bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    safe_content = str(content or "")
    if safe_content.startswith("\ufeff"):
        safe_content = safe_content.lstrip("\ufeff")

    encoded = safe_content.encode("utf-8")
    if keep_bom:
        encoded = b"\xef\xbb\xbf" + encoded

    path.write_bytes(encoded)


def _apply_indent_to_new_text(*, base_old_line: str, new_text: str) -> list[str]:
    indent = _leading_ws(base_old_line)
    normalized_new = str(new_text or "").replace("\r\n", "\n").replace("\r", "\n")
    new_lines = normalized_new.split("\n")

    if len(new_lines) == 1:
        stripped = new_lines[0].strip()
        if not stripped:
            return [new_lines[0]]
        if new_lines[0].startswith(indent):
            return [new_lines[0]]
        return [indent + stripped]

    result: list[str] = []
    for line in new_lines:
        if line == "":
            result.append("")
            continue
        if line.startswith(indent):
            result.append(line)
            continue
        result.append(indent + line.lstrip(" \t"))
    return result


def _find_exact_block(lines: list[str], old_text: str) -> list[int]:
    old_lines = str(old_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not old_lines or old_lines == [""]:
        return []

    matches: list[int] = []
    width = len(old_lines)
    for index in range(0, len(lines) - width + 1):
        if lines[index : index + width] == old_lines:
            matches.append(index)
    return matches


def _find_single_line_stripped(lines: list[str], old_text: str) -> list[int]:
    target = str(old_text or "").strip()
    if not target:
        return []
    return [index for index, line in enumerate(lines) if line.strip() == target]


def _count_changed_lines(before_lines: list[str], after_lines: list[str]) -> dict[str, int]:
    import difflib

    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    inserted = 0
    removed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed += max(0, i2 - i1)
        inserted += max(0, j2 - j1)

    return {
        "inserted": inserted,
        "removed": removed,
        "changed_total": inserted + removed,
    }


def _safety_edit_size_check(
    *,
    before_lines: list[str],
    after_lines: list[str],
    max_changed_lines: int = DEFAULT_MAX_CHANGED_LINES,
    max_inserted_lines: int = DEFAULT_MAX_INSERTED_LINES,
    max_removed_lines: int = DEFAULT_MAX_REMOVED_LINES,
) -> dict[str, Any]:
    counts = _count_changed_lines(before_lines, after_lines)

    if counts["changed_total"] > max_changed_lines:
        return {
            "ok": False,
            "reason": f"changed line count exceeds limit: {counts['changed_total']} > {max_changed_lines}",
            "counts": counts,
            "limits": {
                "max_changed_lines": max_changed_lines,
                "max_inserted_lines": max_inserted_lines,
                "max_removed_lines": max_removed_lines,
            },
        }

    if counts["inserted"] > max_inserted_lines:
        return {
            "ok": False,
            "reason": f"inserted line count exceeds limit: {counts['inserted']} > {max_inserted_lines}",
            "counts": counts,
            "limits": {
                "max_changed_lines": max_changed_lines,
                "max_inserted_lines": max_inserted_lines,
                "max_removed_lines": max_removed_lines,
            },
        }

    if counts["removed"] > max_removed_lines:
        return {
            "ok": False,
            "reason": f"removed line count exceeds limit: {counts['removed']} > {max_removed_lines}",
            "counts": counts,
            "limits": {
                "max_changed_lines": max_changed_lines,
                "max_inserted_lines": max_inserted_lines,
                "max_removed_lines": max_removed_lines,
            },
        }

    return {
        "ok": True,
        "reason": "edit size guard passed",
        "counts": counts,
        "limits": {
            "max_changed_lines": max_changed_lines,
            "max_inserted_lines": max_inserted_lines,
            "max_removed_lines": max_removed_lines,
        },
    }


def _function_boundary_guard(
    *,
    function_target: dict[str, Any],
    replacement_start: int,
    replacement_old_width: int,
    replacement_new_width: int,
) -> dict[str, Any]:
    if not function_target.get("applied"):
        return {
            "ok": True,
            "applied": False,
            "reason": "no function target requested",
        }

    function_start = int(function_target["start_index"])
    function_end = int(function_target["end_index"])
    old_end = replacement_start + replacement_old_width - 1

    if replacement_start < function_start or old_end > function_end:
        return {
            "ok": False,
            "applied": True,
            "reason": "replacement target escapes function boundary",
            "function_range": {
                "start_index": function_start,
                "end_index": function_end,
            },
            "replacement_range": {
                "start_index": replacement_start,
                "old_end_index": old_end,
                "old_width": replacement_old_width,
                "new_width": replacement_new_width,
            },
        }

    # Conservative expansion guard:
    # the edit may insert more lines than it removes, but the anchor must remain inside function.
    # Python syntax verification and AST check validate whether resulting structure is legal.
    return {
        "ok": True,
        "applied": True,
        "reason": "function boundary guard passed",
        "function_range": {
            "start_index": function_start,
            "end_index": function_end,
        },
        "replacement_range": {
            "start_index": replacement_start,
            "old_end_index": old_end,
            "old_width": replacement_old_width,
            "new_width": replacement_new_width,
        },
    }


def _unified_diff_text(old: str, new: str, file_path: str) -> str:
    import difflib

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )


def _parse_python_ast(content: str, *, file_path: str) -> dict[str, Any]:
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return {
            "ok": False,
            "error_type": "SyntaxError",
            "message": exc.msg,
            "lineno": exc.lineno,
            "offset": exc.offset,
            "text": exc.text,
        }

    summary: dict[str, int] = {
        "FunctionDef": 0,
        "AsyncFunctionDef": 0,
        "ClassDef": 0,
        "Return": 0,
        "Assign": 0,
        "AnnAssign": 0,
        "Expr": 0,
        "If": 0,
        "For": 0,
        "While": 0,
        "Try": 0,
        "With": 0,
        "Import": 0,
        "ImportFrom": 0,
    }

    for node in ast.walk(tree):
        name = type(node).__name__
        if name in summary:
            summary[name] += 1

    return {
        "ok": True,
        "summary": summary,
    }


def _find_ast_return_lines(content: str, *, file_path: str) -> set[int]:
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            lines.add(int(getattr(node, "lineno", 0) or 0))
    return lines


def _find_ast_return_fallback_line(
    *,
    content: str,
    lines: list[str],
    file_path: str,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    """
    AST fallback for return-style edits.

    Used only when normal exact/stripped string matching fails.

    Conservative behavior:
    - Only applies to Python files.
    - Only applies when old_text or new_text looks return-related.
    - Requires the current file to parse.
    - Requires exactly one AST Return candidate line.
    - Returns the zero-based line index to rewrite.
    """
    if not file_path.lower().endswith(".py"):
        return {
            "ok": False,
            "reason": "not a Python file",
        }

    old_stripped = str(old_text or "").strip()
    new_lines = str(new_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    new_has_return = any(line.strip().startswith("return ") for line in new_lines)
    old_looks_return = old_stripped.startswith("return ")

    if not old_looks_return and not new_has_return:
        return {
            "ok": False,
            "reason": "AST fallback only handles return-style edits",
        }

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return {
            "ok": False,
            "reason": f"current Python file does not parse: {exc.msg}",
            "lineno": exc.lineno,
            "offset": exc.offset,
        }

    candidates: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return):
            continue

        lineno = int(getattr(node, "lineno", 0) or 0)
        if lineno <= 0 or lineno > len(lines):
            continue

        source_line = lines[lineno - 1]
        candidates.append(
            {
                "lineno": lineno,
                "index": lineno - 1,
                "source_line": source_line,
                "stripped": source_line.strip(),
            }
        )

    if len(candidates) != 1:
        return {
            "ok": False,
            "reason": f"AST return fallback requires exactly one Return node; found {len(candidates)}",
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    candidate = candidates[0]
    return {
        "ok": True,
        "reason": "selected unique AST Return node fallback",
        "match_mode": "ast_unique_return_fallback",
        "index": candidate["index"],
        "lineno": candidate["lineno"],
        "source_line": candidate["source_line"],
        "candidates": candidates,
    }


def _find_function_target_range(
    *,
    content: str,
    lines: list[str],
    file_path: str,
    function_name: str,
) -> dict[str, Any]:
    """
    Find a unique function or async function by name.

    Returns zero-based inclusive line range for the function body span.
    """
    if not function_name:
        return {
            "ok": True,
            "applied": False,
            "reason": "no function target requested",
        }

    if not file_path.lower().endswith(".py"):
        return {
            "ok": False,
            "reason": "function targeting only supports Python files",
            "function_name": function_name,
        }

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return {
            "ok": False,
            "reason": f"current Python file does not parse: {exc.msg}",
            "lineno": exc.lineno,
            "offset": exc.offset,
            "function_name": function_name,
        }

    matches: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue

        lineno = int(getattr(node, "lineno", 0) or 0)
        end_lineno = int(getattr(node, "end_lineno", 0) or 0)
        if lineno <= 0:
            continue
        if end_lineno <= 0:
            end_lineno = lineno

        matches.append(
            {
                "name": node.name,
                "type": type(node).__name__,
                "lineno": lineno,
                "end_lineno": end_lineno,
                "start_index": lineno - 1,
                "end_index": min(end_lineno - 1, len(lines) - 1),
            }
        )

    if len(matches) != 1:
        return {
            "ok": False,
            "reason": f"function target requires exactly one match; found {len(matches)}",
            "function_name": function_name,
            "match_count": len(matches),
            "matches": matches,
        }

    result = dict(matches[0])
    result.update(
        {
            "ok": True,
            "applied": True,
            "reason": "selected unique function target",
            "function_name": function_name,
        }
    )
    return result


def _filter_indexes_to_range(indexes: list[int], *, target_range: dict[str, Any]) -> list[int]:
    if not target_range.get("applied"):
        return indexes

    start = int(target_range["start_index"])
    end = int(target_range["end_index"])
    return [index for index in indexes if start <= index <= end]


def _find_ast_return_fallback_line_in_range(
    *,
    content: str,
    lines: list[str],
    file_path: str,
    old_text: str,
    new_text: str,
    target_range: dict[str, Any],
) -> dict[str, Any]:
    """
    AST Return fallback restricted to a selected function range.
    """
    if not target_range.get("applied"):
        return _find_ast_return_fallback_line(
            content=content,
            lines=lines,
            file_path=file_path,
            old_text=old_text,
            new_text=new_text,
        )

    base = _find_ast_return_fallback_line(
        content=content,
        lines=lines,
        file_path=file_path,
        old_text=old_text,
        new_text=new_text,
    )

    # If global fallback failed because there are multiple Return nodes,
    # re-run candidate selection with function range restriction.
    if not file_path.lower().endswith(".py"):
        return base

    old_stripped = str(old_text or "").strip()
    new_lines = str(new_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    new_has_return = any(line.strip().startswith("return ") for line in new_lines)
    old_looks_return = old_stripped.startswith("return ")

    if not old_looks_return and not new_has_return:
        return {
            "ok": False,
            "reason": "AST fallback only handles return-style edits",
            "function_target": target_range,
        }

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return {
            "ok": False,
            "reason": f"current Python file does not parse: {exc.msg}",
            "lineno": exc.lineno,
            "offset": exc.offset,
            "function_target": target_range,
        }

    range_start = int(target_range["start_index"])
    range_end = int(target_range["end_index"])

    candidates: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return):
            continue

        lineno = int(getattr(node, "lineno", 0) or 0)
        index = lineno - 1
        if lineno <= 0 or index < range_start or index > range_end or lineno > len(lines):
            continue

        source_line = lines[index]
        candidates.append(
            {
                "lineno": lineno,
                "index": index,
                "source_line": source_line,
                "stripped": source_line.strip(),
            }
        )

    if len(candidates) != 1:
        return {
            "ok": False,
            "reason": f"function AST return fallback requires exactly one Return node; found {len(candidates)}",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "function_target": target_range,
        }

    candidate = candidates[0]
    return {
        "ok": True,
        "reason": "selected unique AST Return node inside function target",
        "match_mode": "ast_function_return_fallback",
        "index": candidate["index"],
        "lineno": candidate["lineno"],
        "source_line": candidate["source_line"],
        "candidates": candidates,
        "function_target": target_range,
    }


def _ast_safety_check(
    *,
    file_path: str,
    before: str,
    after: str,
    start_line_1based: int,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    if not file_path.lower().endswith(".py"):
        return {
            "ok": True,
            "applied": False,
            "reason": "not a Python file",
        }

    before_ast = _parse_python_ast(before, file_path=file_path)
    after_ast = _parse_python_ast(after, file_path=file_path)

    if not after_ast.get("ok"):
        return {
            "ok": False,
            "applied": True,
            "reason": "edited Python file does not parse",
            "before_ast": before_ast,
            "after_ast": after_ast,
        }

    old_is_return = str(old_text or "").strip().startswith("return ")
    new_contains_return = any(
        line.strip().startswith("return ")
        for line in str(new_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    )

    return_lines = _find_ast_return_lines(before, file_path=file_path)
    return_line_check = {
        "required": bool(before_ast.get("ok") and old_is_return),
        "selected_line": start_line_1based,
        "known_return_lines": sorted(return_lines),
        "ok": True,
    }

    if before_ast.get("ok") and old_is_return:
        return_line_check["ok"] = start_line_1based in return_lines
        if not return_line_check["ok"]:
            return {
                "ok": False,
                "applied": True,
                "reason": "old_text looks like return statement but selected line is not an AST Return node",
                "before_ast": before_ast,
                "after_ast": after_ast,
                "return_line_check": return_line_check,
            }

    return {
        "ok": True,
        "applied": True,
        "reason": "Python AST safety check passed",
        "before_ast": before_ast,
        "after_ast": after_ast,
        "return_line_check": return_line_check,
        "new_contains_return": new_contains_return,
    }


def _direct_controlled_replace(
    *,
    task: str,
    repo_root: str | Path,
    allow_core: bool,
) -> dict[str, Any]:
    parsed = _parse_simple_replace_task(task)
    if not parsed:
        return {
            "ok": False,
            "status": "not_applicable",
            "reason": "task is not simple controlled replace format",
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    file_path = parsed["file_path"]
    function_name = parsed.get("function_name", "")
    old_text = parsed["old_text"]
    new_text = parsed["new_text"]

    target_path = _resolve_target_path(file_path, repo_root=repo_root, allow_core=allow_core)
    if not target_path.exists():
        return {
            "ok": False,
            "status": "failed",
            "reason": "target file does not exist",
            "file_path": file_path,
            "resolved_path": str(target_path),
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    snapshot = _read_text_snapshot(target_path)
    before = snapshot.content
    lines, newline, had_final_newline = _split_keep_style(before)

    function_target = _find_function_target_range(
        content=before,
        lines=lines,
        file_path=file_path,
        function_name=function_name,
    )
    if not function_target.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason": f"function target failed: {function_target.get('reason')}",
            "file_path": file_path,
            "function_name": function_name,
            "function_target": function_target,
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    exact_matches = _filter_indexes_to_range(
        _find_exact_block(lines, old_text),
        target_range=function_target,
    )
    match_mode = "exact_block"
    if function_target.get("applied"):
        match_mode = "function_exact_block"

    if len(exact_matches) == 1:
        start = exact_matches[0]
        old_width = len(old_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
        base_old_line = lines[start]
    elif len(exact_matches) > 1:
        return {
            "ok": False,
            "status": "failed",
            "reason": f"exact old_text match is ambiguous; found {len(exact_matches)} matches",
            "file_path": file_path,
            "match_count": len(exact_matches),
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }
    else:
        if "\n" in old_text or "\r" in old_text:
            return {
                "ok": False,
                "status": "failed",
                "reason": "multi-line old_text was not found exactly",
                "file_path": file_path,
                "match_count": 0,
                "task_text": task,
                "code_chain_version": CODE_CHAIN_VERSION,
            }

        stripped_matches = _filter_indexes_to_range(
            _find_single_line_stripped(lines, old_text),
            target_range=function_target,
        )
        match_mode = "single_line_stripped"
        if function_target.get("applied"):
            match_mode = "function_single_line_stripped"

        if len(stripped_matches) != 1:
            ast_fallback = _find_ast_return_fallback_line_in_range(
                content=before,
                lines=lines,
                file_path=file_path,
                old_text=old_text,
                new_text=new_text,
                target_range=function_target,
            )

            if not ast_fallback.get("ok"):
                return {
                    "ok": False,
                    "status": "failed",
                    "reason": (
                        f"stripped old_text fallback requires exactly one line match; "
                        f"found {len(stripped_matches)}; AST fallback failed: {ast_fallback.get('reason')}"
                    ),
                    "file_path": file_path,
                    "match_count": len(stripped_matches),
                    "ast_fallback": ast_fallback,
                    "task_text": task,
                    "code_chain_version": CODE_CHAIN_VERSION,
                }

            match_mode = str(ast_fallback.get("match_mode") or "ast_unique_return_fallback")
            start = int(ast_fallback.get("index"))
            old_width = 1
            base_old_line = str(ast_fallback.get("source_line") or lines[start])
        else:
            start = stripped_matches[0]
            old_width = 1
            base_old_line = lines[start]

    replacement_lines = _apply_indent_to_new_text(base_old_line=base_old_line, new_text=new_text)

    boundary_guard = _function_boundary_guard(
        function_target=function_target,
        replacement_start=start,
        replacement_old_width=old_width,
        replacement_new_width=len(replacement_lines),
    )
    if not boundary_guard.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason": f"function boundary guard failed: {boundary_guard.get('reason')}",
            "file_path": file_path,
            "match_mode": match_mode,
            "start_line": start + 1,
            "function_name": function_name,
            "function_target": function_target,
            "boundary_guard": boundary_guard,
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    after_lines = lines[:start] + replacement_lines + lines[start + old_width :]
    edit_size_guard = _safety_edit_size_check(
        before_lines=lines,
        after_lines=after_lines,
    )
    if not edit_size_guard.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason": f"edit size guard failed: {edit_size_guard.get('reason')}",
            "file_path": file_path,
            "match_mode": match_mode,
            "start_line": start + 1,
            "function_name": function_name,
            "function_target": function_target,
            "boundary_guard": boundary_guard,
            "edit_size_guard": edit_size_guard,
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    after = _join_keep_style(after_lines, newline, had_final_newline)

    ast_check = _ast_safety_check(
        file_path=file_path,
        before=before,
        after=after,
        start_line_1based=start + 1,
        old_text=old_text,
        new_text=new_text,
    )

    if not ast_check.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason": f"AST safety check failed: {ast_check.get('reason')}",
            "file_path": file_path,
            "match_mode": match_mode,
            "start_line": start + 1,
            "ast_check": ast_check,
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        }

    changed = before != after
    if changed:
        backup_path = target_path.with_name(target_path.name + f".bak_v20_{int(time.time())}")
        _write_text_file(backup_path, before, keep_bom=snapshot.had_bom)
        _write_text_file(target_path, after, keep_bom=False)
    else:
        backup_path = None

    diff = _unified_diff_text(before, after, file_path)

    return {
        "ok": True,
        "status": "success",
        "handled": True,
        "forced_route": True,
        "tool_name": "self_edit_direct_replace",
        "reason": "direct controlled replace applied" if changed else "direct controlled replace found no changes",
        "payload": {
            "status": "ready",
            "file_path": file_path,
            "mode": "direct_controlled_replace",
            "operation": "controlled_replace",
            "old_text": old_text,
            "new_text": new_text,
            "old_line": base_old_line,
            "match_mode": match_mode,
            "function_name": function_name,
            "function_target": function_target,
            "boundary_guard": boundary_guard,
            "edit_size_guard": edit_size_guard,
            "replacement_line_count": len(replacement_lines),
            "ast_safety": ast_check,
            "io_safety": {
                "encoding": snapshot.encoding,
                "had_bom": snapshot.had_bom,
                "bom_stripped_for_processing": snapshot.had_bom,
                "write_policy": "utf-8-no-bom",
                "newline": repr(snapshot.newline),
            },
            "code_chain_version": CODE_CHAIN_VERSION,
            "task_text": task,
        },
        "tool_result": {
            "ok": True,
            "status": "success",
            "file_path": file_path,
            "changed_files": [file_path] if changed else [],
            "selected_files": [file_path],
            "applied_to_workspace": True,
            "backup_path": str(backup_path) if backup_path else None,
            "diff": diff,
            "report": (
                "[SELF EDIT DIRECT CONTROLLED REPLACE]\n"
                f"Selected files: {file_path}\n"
                f"Changed files : {file_path if changed else '(none)'}\n"
                f"Match mode    : {match_mode}\n"
                f"Function      : {function_name if function_name else '(none)'}\n"
                f"Lines inserted: {len(replacement_lines)}\n"
                f"Boundary guard: {boundary_guard.get('reason')}\n"
                f"Size guard    : {edit_size_guard.get('reason')} {edit_size_guard.get('counts')}\n"
                f"AST safety    : {ast_check.get('reason')}\n"
                f"I/O safety    : utf-8-no-bom write; bom_stripped={snapshot.had_bom}\n"
                f"[DIFF]\n{diff if diff else '(no changes)'}"
            ),
            "task_text": task,
            "code_chain_version": CODE_CHAIN_VERSION,
        },
        "selected_files": [file_path],
        "diff": diff,
        "error": None,
        "applied_to_workspace": True,
        "workspace_path": str(target_path),
        "backup_path": str(backup_path) if backup_path else None,
        "task_text": task,
        "code_chain_version": CODE_CHAIN_VERSION,
    }


def _extract_file_path_from_verify_stderr(stderr: str) -> str:
    text = str(stderr or "")
    match = re.search(r"\(([^()]+\.py),\s*line\s+\d+\)", text)
    if match:
        return _normalize_path_text(match.group(1))
    return ""


def _repair_first_unindented_python_block_body(
    *,
    file_path: str,
    repo_root: str | Path,
    allow_core: bool,
) -> dict[str, Any]:
    target_path = _resolve_target_path(file_path, repo_root=repo_root, allow_core=allow_core)
    if not target_path.exists():
        return {
            "ok": False,
            "reason": "target file does not exist",
            "file_path": file_path,
        }

    snapshot = _read_text_snapshot(target_path)
    before = snapshot.content
    lines, newline, had_final_newline = _split_keep_style(before)

    block_header_re = re.compile(r"^\s*(def|class|if|elif|else|for|while|try|except|finally|with)\b.*:\s*(#.*)?$")
    for index in range(0, len(lines) - 1):
        line = lines[index]
        next_line = lines[index + 1]

        if not block_header_re.match(line):
            continue
        if not next_line.strip():
            continue
        if _leading_ws(next_line) != "":
            continue

        base_indent = _leading_ws(line)
        fixed_next = base_indent + "    " + next_line.lstrip(" \t")
        new_lines = list(lines)
        new_lines[index + 1] = fixed_next
        after = _join_keep_style(new_lines, newline, had_final_newline)

        ast_check = _ast_safety_check(
            file_path=file_path,
            before=before,
            after=after,
            start_line_1based=index + 2,
            old_text=next_line,
            new_text=fixed_next,
        )
        if not ast_check.get("ok"):
            return {
                "ok": False,
                "reason": f"indentation repair blocked by AST check: {ast_check.get('reason')}",
                "file_path": file_path,
                "ast_check": ast_check,
            }

        backup_path = target_path.with_name(target_path.name + f".bak_indent_v20_{int(time.time())}")
        _write_text_file(backup_path, before, keep_bom=snapshot.had_bom)
        _write_text_file(target_path, after, keep_bom=False)

        return {
            "ok": True,
            "type": "indentation_repair_after_verify_failure",
            "reason": "repaired one unindented Python block body line",
            "file_path": file_path,
            "resolved_path": str(target_path),
            "backup_path": str(backup_path),
            "block_line": index + 1,
            "repaired_line": index + 2,
            "old_line": next_line,
            "new_line": fixed_next,
            "diff": _unified_diff_text(before, after, file_path),
            "ast_check": ast_check,
            "io_safety": {
                "encoding": snapshot.encoding,
                "had_bom": snapshot.had_bom,
                "bom_stripped_for_processing": snapshot.had_bom,
                "write_policy": "utf-8-no-bom",
                "newline": repr(snapshot.newline),
            },
        }

    return {
        "ok": False,
        "reason": "no safe def/class/block indentation repair candidate found",
        "file_path": file_path,
    }


def _is_controlled_replace_task(task: str) -> bool:
    return bool(_parse_simple_replace_task(task))


def _rule_plan_single_function_return(task: str) -> dict[str, Any]:
    """
    Deterministic v4.1 planner rule.

    Supported form:
        In workspace/shared/sample_code.py function add, change return to 'return x'

    Also supports multi-line replacement text with literal \\n.

    Output:
        Modify function add in workspace/shared/sample_code.py: replace 'return DOES_NOT_EXIST' with '...'

    The old_text placeholder is intentionally allowed because v3/v4 AST fallback
    can locate the unique return inside the named function.
    """
    text = _normalize_text(task)

    patterns = [
        r"^In\s+(.+?\.py)\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*change\s+return\s+to\s+'((?:\\'|[^'])*)'\s*$",
        r"^Change\s+return\s+in\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+?\.py)\s+to\s+'((?:\\'|[^'])*)'\s*$",
        r"^Set\s+return\s+in\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+?\.py)\s+to\s+'((?:\\'|[^'])*)'\s*$",
    ]

    for index, pattern in enumerate(patterns):
        match = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue

        if index == 0:
            file_path = _normalize_path_text(match.group(1))
            function_name = match.group(2)
            new_text = _decode_task_literal(_shell_unquote_single(match.group(3)))
        else:
            function_name = match.group(1)
            file_path = _normalize_path_text(match.group(2))
            new_text = _decode_task_literal(_shell_unquote_single(match.group(3)))

        planned_step = _make_replace_task(
            file_path=f"function {function_name} in {file_path}",
            old_text="return DOES_NOT_EXIST",
            new_text=new_text,
        )

        # _make_replace_task formats "Modify {file_path}: replace ..."
        # We deliberately passed "function X in file.py" as the pseudo path
        # so it becomes a supported v3 task:
        # Modify function X in file.py: replace ...
        return {
            "ok": True,
            "rule": "single_function_return",
            "reason": "planned one function-level return replacement",
            "steps": [planned_step],
            "source_task": task,
        }

    return {
        "ok": False,
        "reason": "no rule-based plan matched",
        "source_task": task,
    }


def _scan_workspace_files(
    *,
    repo_root: str | Path,
    max_files: int = DEFAULT_MAX_WORKSPACE_FILES_FOR_PROMPT,
) -> list[str]:
    root = Path(repo_root).resolve()
    workspace = root / "workspace"

    if not workspace.exists() or not workspace.is_dir():
        return []

    results: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if len(results) >= max_files:
            break

        if not path.is_file():
            continue

        if path.name.startswith("."):
            continue

        suffix = path.suffix.lower()
        if suffix not in SAFE_TEXT_SUFFIXES:
            continue

        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue

        normalized = str(relative).replace("\\", "/")
        if normalized.endswith(".bak") or ".bak_" in normalized:
            continue

        results.append(normalized)

    return results


def _is_planned_path_in_available_files(file_path: str, available_files: list[str]) -> bool:
    normalized = _normalize_path_text(file_path)
    if not available_files:
        return normalized.startswith("workspace/")
    return normalized in set(available_files)


def _scan_workspace_python_functions(
    *,
    repo_root: str | Path,
    available_files: list[str] | None = None,
    max_items: int = 120,
) -> list[dict[str, Any]]:
    """
    Build a function index for workspace Python files.

    v5.6.4 reliability rule:
    - Use os.walk instead of relying only on Path.rglob.
    - Do not let available_files prompt limits suppress Python discovery.
    - Always include workspace/shared/sample_code.py when present.
    - Return parse errors as diagnostics instead of silently hiding them.
    """
    root = Path(repo_root).resolve()
    workspace = root / "workspace"

    candidate_relatives: set[str] = set()

    # Known local smoke target used by the self-edit loop tests. This is not
    # used as an edit rule; it only ensures the function index can see the file
    # if it exists and the general scan unexpectedly misses it.
    known_sample = root / "workspace" / "shared" / "sample_code.py"
    if known_sample.exists() and known_sample.is_file():
        try:
            candidate_relatives.add(str(known_sample.resolve().relative_to(root)).replace("\\", "/"))
        except ValueError:
            pass

    # Direct workspace Python scan.
    if workspace.exists() and workspace.is_dir():
        for dirpath, dirnames, filenames in os.walk(workspace):
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".")
                and "__pycache__" not in name
                and ".git" not in name
            ]

            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                if filename.startswith("."):
                    continue
                if ".bak_" in filename:
                    continue

                path = Path(dirpath) / filename
                try:
                    relative = path.resolve().relative_to(root)
                except ValueError:
                    continue
                candidate_relatives.add(str(relative).replace("\\", "/"))

    # Also include Python files already discovered by the workspace file scanner.
    for item in list(available_files or []):
        normalized = _normalize_path_text(item)
        if normalized.startswith("workspace/") and normalized.endswith(".py"):
            candidate_relatives.add(normalized)

    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for relative in sorted(candidate_relatives):
        if len(items) >= max_items:
            break

        path = (root / relative).resolve()
        if not path.exists() or not path.is_file():
            diagnostics.append(
                {
                    "file_path": relative,
                    "error": "candidate path does not exist",
                }
            )
            continue

        try:
            snapshot = _read_text_snapshot(path)
            tree = ast.parse(snapshot.content, filename=relative)
        except Exception as exc:
            diagnostics.append(
                {
                    "file_path": relative,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        found_any = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            found_any = True
            items.append(
                {
                    "file_path": relative,
                    "function_name": node.name,
                    "type": type(node).__name__,
                    "lineno": int(getattr(node, "lineno", 0) or 0),
                    "end_lineno": int(getattr(node, "end_lineno", 0) or 0),
                }
            )

            if len(items) >= max_items:
                break

        if not found_any:
            diagnostics.append(
                {
                    "file_path": relative,
                    "error": "no function definitions found",
                }
            )

    # Keep diagnostics small and visible if no functions were found.
    if not items:
        for diagnostic in diagnostics[:20]:
            items.append(
                {
                    "file_path": diagnostic.get("file_path", ""),
                    "function_name": "",
                    "type": "scan_diagnostic",
                    "lineno": 0,
                    "end_lineno": 0,
                    "error": diagnostic.get("error", ""),
                }
            )

    return items

def _format_function_index_for_prompt(function_index: list[dict[str, Any]]) -> str:
    real_items = [
        item
        for item in function_index
        if item.get("function_name") and item.get("type") not in {"parse_error", "scan_diagnostic"}
    ]

    if not real_items:
        diagnostics = [
            item
            for item in function_index
            if item.get("type") in {"parse_error", "scan_diagnostic"} or item.get("error")
        ]
        if diagnostics:
            return "\n".join(
                f"- diagnostic {item.get('file_path', '')}: {item.get('error', '')}"
                for item in diagnostics[:20]
            )
        return "- (none detected)"

    lines: list[str] = []
    for item in real_items:
        lines.append(
            f"- {item.get('file_path', '')}: function {item.get('function_name', '')} "
            f"at line {item.get('lineno', '')}"
        )
    return "\n".join(lines)

def _python_file_contains_function(
    *,
    repo_root: str | Path,
    file_path: str,
    function_name: str,
) -> dict[str, Any]:
    if not function_name:
        return {
            "ok": True,
            "applied": False,
            "reason": "no function target requested",
        }

    normalized = _normalize_path_text(file_path)
    if not normalized.endswith(".py"):
        return {
            "ok": False,
            "applied": True,
            "reason": "function target was requested for a non-Python file",
            "file_path": normalized,
            "function_name": function_name,
        }

    root = Path(repo_root).resolve()
    path = (root / normalized).resolve()

    if not path.exists():
        return {
            "ok": False,
            "applied": True,
            "reason": "function target file does not exist",
            "file_path": normalized,
            "function_name": function_name,
        }

    try:
        snapshot = _read_text_snapshot(path)
        tree = ast.parse(snapshot.content, filename=normalized)
    except Exception as exc:
        return {
            "ok": False,
            "applied": True,
            "reason": f"unable to parse function target file: {type(exc).__name__}: {exc}",
            "file_path": normalized,
            "function_name": function_name,
        }

    matches: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            matches.append(
                {
                    "function_name": node.name,
                    "type": type(node).__name__,
                    "lineno": int(getattr(node, "lineno", 0) or 0),
                    "end_lineno": int(getattr(node, "end_lineno", 0) or 0),
                }
            )

    if len(matches) != 1:
        return {
            "ok": False,
            "applied": True,
            "reason": f"function target requires exactly one match in selected file; found {len(matches)}",
            "file_path": normalized,
            "function_name": function_name,
            "matches": matches,
        }

    return {
        "ok": True,
        "applied": True,
        "reason": "function target exists in selected file",
        "file_path": normalized,
        "function_name": function_name,
        "match": matches[0],
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    """
    Extract one JSON object from model output.

    v5.1 intentionally tolerates noisy local model output:
    - direct JSON object;
    - markdown fenced JSON;
    - extra text before/after JSON.

    It still only accepts a JSON object.
    """
    raw = str(text or "").strip()
    if not raw:
        return {}

    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        try:
            value = json.loads(fenced.group(1))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            pass

    candidates: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escape = False

    for index, char in enumerate(raw):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue

        if char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(raw[start : index + 1])
                    start = -1

    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue

    return {}


def _format_available_files_for_prompt(files: list[str]) -> str:
    if not files:
        return "- workspace/shared/sample_code.py"

    return "\n".join(f"- {path}" for path in files)


def _build_llm_planner_prompt(
    task: str,
    available_files: list[str] | None = None,
    function_index: list[dict[str, Any]] | None = None,
) -> str:
    available = _format_available_files_for_prompt(list(available_files or []))
    functions = _format_function_index_for_prompt(list(function_index or []))

    return f"""
You are ZERO's guarded local code-edit planner.

OUTPUT CONTRACT:
Return ONLY one valid JSON object.
No markdown.
No comments.
No explanations.
No text before JSON.
No text after JSON.

Required JSON schema:
{{"steps":["Modify function NAME in workspace/path/file.py: replace 'old' with 'new'"]}}

Available workspace files:
{available}

Detected Python functions:
{functions}

Allowed step formats:
1. Function-level single-line replace:
{{"steps":["Modify function add in workspace/shared/sample_code.py: replace 'return DOES_NOT_EXIST' with 'return a + b'"]}}

2. Function-level multi-line replace:
{{"steps":["Modify function add in workspace/shared/sample_code.py: replace 'return DOES_NOT_EXIST' with 'result = a + b\\nreturn result'"]}}

Planning rules:
1. Every step MUST be a controlled replace instruction.
2. Use ONLY paths from "Available workspace files".
3. If the task mentions a function, use ONLY a matching path from "Detected Python functions".
4. If Detected Python functions contains 'function add', choose that exact file path.
5. Do not choose files that do not contain the named function.
6. Prefer function-level targeting.
7. Use workspace/... paths only.
8. Do not invent paths.
9. Do not output shell commands.
10. Do not delete, rename, move, chmod, curl, wget, run tests, or execute commands.
11. Do not create broad edits.
12. If uncertain, output exactly {{"steps":[]}}.
13. JSON string newlines MUST be escaped as \\n.
14. For Python return fixes, the replacement should contain a return statement.

Task:
{task}
""".strip()

def _normalize_llm_planner_command(command: str) -> str:
    """
    v5.1 helper.

    If the command appears to be Ollama and has no explicit format option,
    add JSON mode automatically. This improves local planner stability while
    remaining transparent in the returned command metadata.
    """
    value = _normalize_text(command)
    lowered = value.lower()

    if "ollama run" in lowered and "--format" not in lowered:
        return value + " --format json"

    return value


def _run_ollama_planner_http(
    *,
    task: str,
    ollama_model: str,
    ollama_url: str,
    timeout_seconds: int = DEFAULT_LLM_PLANNER_TIMEOUT_SECONDS,
    available_files: list[str] | None = None,
    function_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Built-in local Ollama planner.

    This avoids PowerShell/WSL shell quoting and interactive command deadlocks.
    Ollama must already be serving the HTTP API.
    """
    model = _normalize_text(ollama_model)
    if not model:
        return {
            "ok": False,
            "reason": "ollama model is empty",
        }

    base_url = _normalize_text(ollama_url) or "http://127.0.0.1:11434"
    endpoint = base_url.rstrip("/") + "/api/generate"

    payload = {
        "model": model,
        "prompt": _build_llm_planner_prompt(task, available_files=available_files, function_index=function_index),
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "top_p": 0.2,
        },
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "reason": f"ollama planner HTTP request failed: {exc}",
            "endpoint": endpoint,
            "model": model,
        }
    except TimeoutError:
        return {
            "ok": False,
            "reason": f"ollama planner timed out after {timeout_seconds}s",
            "endpoint": endpoint,
            "model": model,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"ollama planner failed: {type(exc).__name__}: {exc}",
            "endpoint": endpoint,
            "model": model,
        }

    elapsed = time.time() - started

    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "reason": "ollama HTTP response was not valid JSON",
            "raw": raw,
            "endpoint": endpoint,
            "model": model,
            "elapsed_seconds": elapsed,
        }

    model_text = str(outer.get("response") or "")
    data_obj = _extract_json_object(model_text)
    if not data_obj:
        return {
            "ok": False,
            "reason": "ollama planner response did not contain valid planner JSON",
            "ollama_response": outer,
            "model_text": model_text,
            "endpoint": endpoint,
            "model": model,
            "elapsed_seconds": elapsed,
        }

    steps = data_obj.get("steps")
    if not isinstance(steps, list):
        return {
            "ok": False,
            "reason": "ollama planner JSON missing list field: steps",
            "planner_json": data_obj,
            "ollama_response": outer,
            "endpoint": endpoint,
            "model": model,
            "elapsed_seconds": elapsed,
        }

    cleaned_steps: list[str] = []
    for item in steps:
        if isinstance(item, str) and item.strip():
            cleaned_steps.append(item.strip())

    return {
        "ok": True,
        "reason": "ollama planner returned candidate steps",
        "mode": "ollama_http",
        "steps": cleaned_steps,
        "planner_json": data_obj,
        "ollama_response": outer,
        "endpoint": endpoint,
        "model": model,
        "elapsed_seconds": elapsed,
    }


def _run_llm_planner_command(
    *,
    task: str,
    llm_planner_command: str,
    repo_root: str | Path,
    timeout_seconds: int = DEFAULT_LLM_PLANNER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command = _normalize_llm_planner_command(llm_planner_command)
    if not command:
        return {
            "ok": False,
            "reason": "llm planner command is empty",
        }

    command_available_files = _scan_workspace_files(repo_root=repo_root)
    command_function_index = _scan_workspace_python_functions(
        repo_root=repo_root,
        available_files=command_available_files,
    )
    prompt = _build_llm_planner_prompt(
        task,
        available_files=command_available_files,
        function_index=command_function_index,
    )

    try:
        args = shlex.split(command, posix=False)
    except ValueError:
        args = command.split()

    if not args:
        return {
            "ok": False,
            "reason": "llm planner command produced empty args",
        }

    blocked_fragments = (
        "&&",
        "||",
        ";",
        "|",
        ">",
        "<",
        "`",
        "$(",
        "rm ",
        "del ",
        "erase ",
        "curl ",
        "wget ",
        "powershell",
        "cmd.exe",
        "bash -c",
        "sh -c",
    )
    lowered_command = command.lower()
    if any(fragment in lowered_command for fragment in blocked_fragments):
        return {
            "ok": False,
            "reason": "llm planner command blocked by allowlist guard",
            "command": command,
            "blocked_fragments": [fragment for fragment in blocked_fragments if fragment in lowered_command],
        }

    started = time.time()
    try:
        completed = subprocess.run(
            args,
            input=prompt,
            cwd=str(Path(repo_root).resolve()),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "reason": f"llm planner timed out after {timeout_seconds}s",
            "command": command,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"llm planner failed: {type(exc).__name__}: {exc}",
            "command": command,
        }

    elapsed = time.time() - started
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": f"llm planner returned non-zero exit code {completed.returncode}",
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "elapsed_seconds": elapsed,
        }

    data = _extract_json_object(completed.stdout)
    if not data:
        return {
            "ok": False,
            "reason": "llm planner did not return valid JSON object",
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "elapsed_seconds": elapsed,
        }

    steps = data.get("steps")
    if not isinstance(steps, list):
        return {
            "ok": False,
            "reason": "llm planner JSON missing list field: steps",
            "planner_json": data,
            "elapsed_seconds": elapsed,
        }

    cleaned_steps: list[str] = []
    for item in steps:
        if isinstance(item, str) and item.strip():
            cleaned_steps.append(item.strip())

    return {
        "ok": True,
        "reason": "llm planner returned candidate steps",
        "mode": "llm",
        "steps": cleaned_steps,
        "planner_json": data,
        "elapsed_seconds": elapsed,
        "command": command,
    }


def _sanity_check_planned_step(step: str) -> dict[str, Any]:
    """
    Extra guard for LLM-generated controlled steps.

    This is intentionally conservative. The editor and AST checks still enforce
    the final safety boundary; this rejects obviously bad planner output earlier.
    """
    parsed = _parse_simple_replace_task(step)
    if not parsed:
        return {
            "ok": False,
            "reason": "step is not parseable as a controlled replace task",
        }

    file_path = str(parsed.get("file_path") or "")
    old_text = str(parsed.get("old_text") or "")
    new_text = str(parsed.get("new_text") or "")
    function_name = str(parsed.get("function_name") or "")

    if not file_path.startswith("workspace/"):
        return {
            "ok": False,
            "reason": "planned step target is not under workspace/",
            "file_path": file_path,
        }

    if not old_text.strip():
        return {
            "ok": False,
            "reason": "planned old_text is empty",
        }

    if not new_text.strip():
        return {
            "ok": False,
            "reason": "planned new_text is empty",
        }

    lowered = step.lower()
    blocked = (
        " delete ",
        " remove ",
        " rename ",
        " move ",
        " chmod ",
        " chown ",
        " curl ",
        " wget ",
        " powershell ",
        " cmd.exe ",
        " bash ",
        " rm ",
        " del ",
    )
    for token in blocked:
        if token in f" {lowered} ":
            return {
                "ok": False,
                "reason": f"planned step contains blocked token: {token.strip()}",
            }

    old_return_like = old_text.strip().startswith("return ")
    new_contains_return = any(
        line.strip().startswith("return ")
        for line in new_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    )
    if old_return_like and not new_contains_return:
        return {
            "ok": False,
            "reason": "return-style edit replacement does not contain a return statement",
        }

    if len(new_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")) > DEFAULT_MAX_INSERTED_LINES:
        return {
            "ok": False,
            "reason": "planned replacement has too many lines",
        }

    return {
        "ok": True,
        "reason": "planned step sanity check passed",
        "file_path": file_path,
        "function_name": function_name,
    }


def _validate_planned_steps(
    *,
    steps: list[str],
    allow_core: bool,
    repo_root: str | Path,
    max_steps: int = DEFAULT_MAX_PLANNER_STEPS,
    available_files: list[str] | None = None,
) -> dict[str, Any]:
    if not steps:
        return {
            "ok": False,
            "reason": "planner produced no steps",
            "steps": steps,
        }

    if len(steps) > max_steps:
        return {
            "ok": False,
            "reason": f"planner produced too many steps: {len(steps)} > {max_steps}",
            "steps": steps,
            "max_steps": max_steps,
        }

    validated: list[str] = []
    failures: list[dict[str, Any]] = []

    for index, step in enumerate(steps, start=1):
        try:
            validate_self_edit_task(step, allow_core=allow_core)
            parsed = _parse_simple_replace_task(step)
            if not parsed:
                failures.append(
                    {
                        "index": index,
                        "step": step,
                        "reason": "step is not a supported controlled replace task",
                    }
                )
                continue

            sanity = _sanity_check_planned_step(step)
            if not sanity.get("ok"):
                failures.append(
                    {
                        "index": index,
                        "step": step,
                        "reason": f"step failed sanity check: {sanity.get('reason')}",
                        "sanity": sanity,
                    }
                )
                continue

            file_path = str(parsed.get("file_path") or "")
            if not _is_planned_path_in_available_files(file_path, list(available_files or [])):
                failures.append(
                    {
                        "index": index,
                        "step": step,
                        "reason": "planned file path is not in available workspace files",
                        "file_path": file_path,
                        "available_files": list(available_files or []),
                    }
                )
                continue

            function_name = str(parsed.get("function_name") or "")
            function_check = _python_file_contains_function(
                repo_root=repo_root,
                file_path=file_path,
                function_name=function_name,
            )
            if not function_check.get("ok"):
                failures.append(
                    {
                        "index": index,
                        "step": step,
                        "reason": f"planned function target is invalid: {function_check.get('reason')}",
                        "function_check": function_check,
                    }
                )
                continue

            validated.append(step)
        except Exception as exc:
            failures.append(
                {
                    "index": index,
                    "step": step,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    if failures:
        return {
            "ok": False,
            "reason": "one or more planned steps failed validation",
            "validated_steps": validated,
            "failures": failures,
        }

    return {
        "ok": True,
        "reason": "all planned steps passed validation",
        "steps": validated,
    }

def _llm_plan_steps(
    *,
    task: str,
    repo_root: str | Path,
    allow_core: bool,
    llm_planner_command: str,
    llm_planner_timeout: int,
    ollama_model: str = "",
    ollama_url: str = "http://127.0.0.1:11434",
    llm_planner_retries: int = DEFAULT_LLM_PLANNER_RETRIES,
    available_files: list[str] | None = None,
    function_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    total_attempts = max(1, int(llm_planner_retries) + 1)
    available_files = list(available_files or [])
    function_index = list(function_index or [])

    for attempt_index in range(1, total_attempts + 1):
        if _normalize_text(ollama_model):
            llm_result = _run_ollama_planner_http(
                task=task,
                ollama_model=ollama_model,
                ollama_url=ollama_url,
                timeout_seconds=llm_planner_timeout,
                available_files=available_files,
                function_index=function_index,
            )
        else:
            llm_result = _run_llm_planner_command(
                task=task,
                llm_planner_command=llm_planner_command,
                repo_root=repo_root,
                timeout_seconds=llm_planner_timeout,
            )

        attempt_record: dict[str, Any] = {
            "attempt": attempt_index,
            "llm_result": llm_result,
        }

        if not llm_result.get("ok"):
            attempt_record["ok"] = False
            attempt_record["reason"] = llm_result.get("reason")
            attempts.append(attempt_record)
            continue

        validation = _validate_planned_steps(
            steps=list(llm_result.get("steps") or []),
            allow_core=allow_core,
            repo_root=repo_root,
            available_files=available_files,
        )
        attempt_record["validation"] = validation

        if not validation.get("ok"):
            attempt_record["ok"] = False
            attempt_record["reason"] = validation.get("reason")
            attempts.append(attempt_record)
            continue

        attempt_record["ok"] = True
        attempt_record["reason"] = "llm planner produced validated controlled steps"
        attempts.append(attempt_record)

        return {
            "ok": True,
            "mode": "llm",
            "reason": "llm planner produced validated controlled steps",
            "steps": list(validation.get("steps") or []),
            "llm_result": llm_result,
            "validation": validation,
            "attempts": attempts,
            "source_task": task,
            "available_files": available_files,
            "function_index": function_index,
        }

    last = attempts[-1] if attempts else {}
    return {
        "ok": False,
        "mode": "llm",
        "reason": last.get("reason") or "llm planner failed",
        "llm_result": last.get("llm_result", {}),
        "validation": last.get("validation", {}),
        "attempts": attempts,
        "source_task": task,
        "available_files": available_files,
        "function_index": function_index,
    }


def _rule_based_plan_steps(task: str) -> dict[str, Any]:
    """
    v4.1 conservative planner.

    It never invents broad edits. It either:
    - preserves explicit multi-step controlled tasks;
    - preserves a single controlled replace task;
    - converts one narrow supported natural-language rule into one controlled task.
    """
    explicit_steps = _split_agent_steps(task)
    if len(explicit_steps) > 1:
        return {
            "ok": True,
            "mode": "explicit_multi_step",
            "reason": "task already contains explicit step separators",
            "steps": explicit_steps,
            "source_task": task,
        }

    if _is_controlled_replace_task(task):
        return {
            "ok": True,
            "mode": "already_controlled",
            "reason": "task is already a controlled replace instruction",
            "steps": [task],
            "source_task": task,
        }

    planned = _rule_plan_single_function_return(task)
    if planned.get("ok"):
        return {
            "ok": True,
            "mode": "rule_based",
            "reason": planned.get("reason"),
            "rule": planned.get("rule"),
            "steps": list(planned.get("steps") or []),
            "source_task": task,
        }

    return {
        "ok": False,
        "mode": "unplanned",
        "reason": planned.get("reason") or "no planner rule matched",
        "steps": [],
        "source_task": task,
    }


def _split_agent_steps(task: str) -> list[str]:
    """
    Split explicit multi-step tasks only.

    This is intentionally conservative. It does not ask an LLM to invent edits.
    Supported separators:
        ||STEP||
        ; THEN ;
        THEN
    """
    text = _normalize_text(task)
    if not text:
        return []

    if "||STEP||" in text:
        parts = [item.strip() for item in text.split("||STEP||")]
    elif "; THEN ;" in text:
        parts = [item.strip() for item in text.split("; THEN ;")]
    else:
        parts = re.split(r"\s+THEN\s+", text, flags=re.IGNORECASE)
        parts = [item.strip() for item in parts]

    parts = [item for item in parts if item]
    return parts if parts else [text]


def _is_multi_step_task(task: str) -> bool:
    return len(_split_agent_steps(task)) > 1


def _capture_transaction_snapshot(path: Path) -> TransactionSnapshot:
    snapshot = _read_text_snapshot(path)
    return TransactionSnapshot(
        path=path,
        content=snapshot.content,
        had_bom=snapshot.had_bom,
    )


def _restore_transaction_snapshots(snapshots: dict[str, TransactionSnapshot]) -> list[dict[str, Any]]:
    restored: list[dict[str, Any]] = []
    for key, snapshot in snapshots.items():
        try:
            _write_text_file(snapshot.path, snapshot.content, keep_bom=snapshot.had_bom)
            restored.append(
                {
                    "ok": True,
                    "path": str(snapshot.path),
                    "reason": "restored transaction snapshot",
                }
            )
        except Exception as exc:
            restored.append(
                {
                    "ok": False,
                    "path": str(snapshot.path),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
    return restored


def _target_path_from_task(
    task: str,
    *,
    repo_root: str | Path,
    allow_core: bool,
) -> Path | None:
    parsed = _parse_simple_replace_task(task)
    if not parsed:
        return None

    file_path = parsed.get("file_path", "")
    if not file_path:
        return None

    return _resolve_target_path(file_path, repo_root=repo_root, allow_core=allow_core)


def _run_verify_commands(
    verify_commands: list[str],
    *,
    repo_root: str | Path,
    verify_timeout_seconds: int,
) -> list[VerifyResult]:
    results: list[VerifyResult] = []
    for command in verify_commands:
        results.append(
            run_verify_command(
                command,
                repo_root=repo_root,
                timeout_seconds=verify_timeout_seconds,
            )
        )
    return results


def _run_single_step_self_edit_loop(
    task: str,
    *,
    repo_root: str | Path = DEFAULT_REPO_ROOT,
    verify_commands: list[str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    allow_core: bool = False,
    verify_timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
) -> SelfEditLoopResult:
    task = _normalize_text(task)
    repo_root_path = Path(repo_root).resolve()
    verify_commands = list(verify_commands or [])

    validate_self_edit_task(task, allow_core=allow_core)

    attempts: list[SelfEditAttempt] = []
    current_task = task
    used_tasks = {current_task}

    for attempt_number in range(1, max(1, max_attempts) + 1):
        correction: dict[str, Any] = {}

        direct_result = _direct_controlled_replace(
            task=current_task,
            repo_root=repo_root_path,
            allow_core=allow_core,
        )

        if direct_result.get("status") == "not_applicable":
            run_repo_edit_decision = _load_repo_edit_bridge()
            edit_result = run_repo_edit_decision(current_task, repo_root=str(repo_root_path), force=True)
        else:
            edit_result = direct_result

        edit_ok = _edit_result_ok(edit_result)
        verify_results: list[VerifyResult] = []

        if edit_ok:
            verify_results = _run_verify_commands(
                verify_commands,
                repo_root=repo_root_path,
                verify_timeout_seconds=verify_timeout_seconds,
            )
            verify_ok = all(item.ok for item in verify_results) if verify_results else True

            if not verify_ok:
                indentation_failure = next(
                    (
                        item
                        for item in verify_results
                        if "IndentationError" in item.stderr
                        and "expected an indented block" in item.stderr
                    ),
                    None,
                )

                if indentation_failure is not None:
                    repair_file = _extract_file_path_from_verify_stderr(indentation_failure.stderr)
                    if not repair_file:
                        parsed = _parse_simple_replace_task(current_task)
                        repair_file = parsed.get("file_path", "") if parsed else ""

                    if repair_file:
                        correction = _repair_first_unindented_python_block_body(
                            file_path=repair_file,
                            repo_root=repo_root_path,
                            allow_core=allow_core,
                        )
                    else:
                        correction = {
                            "ok": False,
                            "reason": "unable to determine file path for indentation repair",
                        }

                    if correction.get("ok"):
                        verify_results = _run_verify_commands(
                            verify_commands,
                            repo_root=repo_root_path,
                            verify_timeout_seconds=verify_timeout_seconds,
                        )
                        verify_ok = all(item.ok for item in verify_results) if verify_results else True

            ok = edit_ok and verify_ok
            if ok and correction.get("ok"):
                reason = "edit and verification succeeded after indentation repair"
            elif ok:
                reason = "edit and verification succeeded"
            elif correction:
                reason = f"verification failed; indentation repair failed: {correction.get('reason')}"
            else:
                reason = "verification failed"
        else:
            ok = False
            reason = str(edit_result.get("reason") or edit_result.get("status") or "edit failed")

        attempts.append(
            SelfEditAttempt(
                attempt=attempt_number,
                task=current_task,
                edit_result=edit_result,
                verify_results=verify_results,
                correction=correction,
                ok=ok,
                reason=reason,
            )
        )

        if ok:
            return SelfEditLoopResult(
                ok=True,
                status="success",
                task=task,
                final_task=current_task,
                attempts=attempts,
                max_attempts=max_attempts,
                repo_root=str(repo_root_path),
                final_reason=reason,
            )

        if not _is_old_text_mismatch(edit_result):
            break

        if current_task in used_tasks:
            break

        used_tasks.add(current_task)

    return SelfEditLoopResult(
        ok=False,
        status="failed",
        task=task,
        final_task=current_task,
        attempts=attempts,
        max_attempts=max_attempts,
        repo_root=str(repo_root_path),
        final_reason=attempts[-1].reason if attempts else "no attempts executed",
    )


def run_self_edit_loop(
    task: str,
    *,
    repo_root: str | Path = DEFAULT_REPO_ROOT,
    verify_commands: list[str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    allow_core: bool = False,
    verify_timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
    planner_mode: str = "rule",
    llm_planner_command: str = "",
    llm_planner_timeout: int = DEFAULT_LLM_PLANNER_TIMEOUT_SECONDS,
    ollama_model: str = "",
    ollama_url: str = "http://127.0.0.1:11434",
    llm_planner_retries: int = DEFAULT_LLM_PLANNER_RETRIES,
) -> SelfEditLoopResult:
    """
    v4 Agent Loop entrypoint.

    Single-step tasks use the v3.1 guarded path unchanged.
    Multi-step tasks run as a conservative transaction:
        plan -> execute step -> verify -> observe -> rollback on failure
    """
    task = _normalize_text(task)
    repo_root_path = Path(repo_root).resolve()
    verify_commands = list(verify_commands or [])

    planner_mode = str(planner_mode or "rule").strip().lower()
    if planner_mode not in {"rule", "llm"}:
        planner_mode = "rule"

    available_files = _scan_workspace_files(repo_root=repo_root_path)
    function_index = _scan_workspace_python_functions(
        repo_root=repo_root_path,
        available_files=available_files,
    )

    if planner_mode == "llm":
        plan = _llm_plan_steps(
            task=task,
            repo_root=repo_root_path,
            allow_core=allow_core,
            llm_planner_command=llm_planner_command,
            llm_planner_timeout=llm_planner_timeout,
            ollama_model=ollama_model,
            ollama_url=ollama_url,
            llm_planner_retries=llm_planner_retries,
            available_files=available_files,
        )
        if not plan.get("ok"):
            fallback_plan = _rule_based_plan_steps(task)
            plan["fallback_rule_plan"] = fallback_plan
            if fallback_plan.get("ok"):
                plan = fallback_plan
                plan["mode"] = "rule_fallback_after_llm_failure"
    else:
        plan = _rule_based_plan_steps(task)

    if not plan.get("ok"):
        attempt = SelfEditAttempt(
            attempt=1,
            task=task,
            edit_result={
                "ok": False,
                "status": "failed",
                "reason": f"planning failed: {plan.get('reason')}",
                "planner": plan,
                "code_chain_version": CODE_CHAIN_VERSION,
            },
            verify_results=[],
            correction={},
            ok=False,
            reason=f"planning failed: {plan.get('reason')}",
        )
        return SelfEditLoopResult(
            ok=False,
            status="failed",
            task=task,
            final_task=task,
            attempts=[attempt],
            max_attempts=max_attempts,
            repo_root=str(repo_root_path),
            final_reason=attempt.reason,
        )

    steps = list(plan.get("steps") or [])
    if len(steps) <= 1:
        result = _run_single_step_self_edit_loop(
            steps[0] if steps else task,
            repo_root=repo_root_path,
            verify_commands=verify_commands,
            max_attempts=max_attempts,
            allow_core=allow_core,
            verify_timeout_seconds=verify_timeout_seconds,
        )
        if result.attempts:
            result.attempts[0].edit_result = dict(result.attempts[0].edit_result)
            result.attempts[0].edit_result["planner"] = plan
        result.task = task
        return result

    transaction_snapshots: dict[str, TransactionSnapshot] = {}
    all_attempts: list[SelfEditAttempt] = []
    final_reason = ""
    rollback_result: list[dict[str, Any]] = []

    for step_index, step in enumerate(steps, start=1):
        validate_self_edit_task(step, allow_core=allow_core)

        try:
            target = _target_path_from_task(
                step,
                repo_root=repo_root_path,
                allow_core=allow_core,
            )
            if target is not None and target.exists():
                key = str(target.resolve())
                if key not in transaction_snapshots:
                    transaction_snapshots[key] = _capture_transaction_snapshot(target)
        except Exception as exc:
            rollback_result = _restore_transaction_snapshots(transaction_snapshots)
            attempt = SelfEditAttempt(
                attempt=step_index,
                task=step,
                edit_result={
                    "ok": False,
                    "status": "failed",
                    "reason": f"transaction snapshot failed: {type(exc).__name__}: {exc}",
                    "agent_loop": {
                        "mode": "multi_step_transaction",
                        "step_index": step_index,
                        "step_count": len(steps),
                        "rollback": rollback_result,
                    },
                    "code_chain_version": CODE_CHAIN_VERSION,
                },
                verify_results=[],
                correction={},
                ok=False,
                reason="transaction snapshot failed",
            )
            all_attempts.append(attempt)
            return SelfEditLoopResult(
                ok=False,
                status="failed",
                task=task,
                final_task=step,
                attempts=all_attempts,
                max_attempts=max_attempts,
                repo_root=str(repo_root_path),
                final_reason=attempt.reason,
            )

        step_result = _run_single_step_self_edit_loop(
            step,
            repo_root=repo_root_path,
            verify_commands=verify_commands,
            max_attempts=max_attempts,
            allow_core=allow_core,
            verify_timeout_seconds=verify_timeout_seconds,
        )

        for item in step_result.attempts:
            if isinstance(item.edit_result, dict):
                item.edit_result = dict(item.edit_result)
                item.edit_result["agent_loop"] = {
                    "mode": "multi_step_transaction",
                    "step_index": step_index,
                    "step_count": len(steps),
                    "step_ok": step_result.ok,
                    "rollback_on_failure": True,
                    "planner": plan,
                }
            all_attempts.append(item)

        if not step_result.ok:
            rollback_result = _restore_transaction_snapshots(transaction_snapshots)
            if all_attempts:
                all_attempts[-1].correction = dict(all_attempts[-1].correction or {})
                all_attempts[-1].correction["transaction_rollback"] = rollback_result
                all_attempts[-1].reason = (
                    f"{all_attempts[-1].reason}; transaction rolled back after step {step_index}"
                )

            final_reason = f"multi-step transaction failed at step {step_index}; rolled back"
            return SelfEditLoopResult(
                ok=False,
                status="failed",
                task=task,
                final_task=step,
                attempts=all_attempts,
                max_attempts=max_attempts,
                repo_root=str(repo_root_path),
                final_reason=final_reason,
            )

    final_reason = "multi-step transaction succeeded"
    if all_attempts:
        all_attempts[-1].correction = dict(all_attempts[-1].correction or {})
        all_attempts[-1].correction["transaction"] = {
            "ok": True,
            "mode": "multi_step_transaction",
            "step_count": len(steps),
            "snapshots": list(transaction_snapshots.keys()),
            "rollback": [],
        }

    return SelfEditLoopResult(
        ok=True,
        status="success",
        task=task,
        final_task=steps[-1],
        attempts=all_attempts,
        max_attempts=max_attempts,
        repo_root=str(repo_root_path),
        final_reason=final_reason,
    )


def _read_task_from_file(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZERO conservative self-edit loop with guarded optional LLM planning")
    parser.add_argument("--task", default="", help="Explicit controlled edit task text")
    parser.add_argument("--task-file", default="", help="Read task text from a UTF-8 file")
    parser.add_argument("--repo-root", default=DEFAULT_REPO_ROOT, help="Repository root")
    parser.add_argument("--verify", action="append", default=[], help="Verification command; may be repeated")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--verify-timeout", type=int, default=DEFAULT_VERIFY_TIMEOUT_SECONDS)
    parser.add_argument("--allow-core", action="store_true", help="Allow core/app/services/tests/ui paths")
    parser.add_argument("--planner", choices=["rule", "llm"], default="rule", help="Planner mode; llm is guarded and optional")
    parser.add_argument("--llm-planner-command", default="", help="Command that reads planner prompt from stdin and returns JSON")
    parser.add_argument("--llm-planner-timeout", type=int, default=DEFAULT_LLM_PLANNER_TIMEOUT_SECONDS)
    parser.add_argument("--ollama-model", default="", help="Use built-in Ollama HTTP planner with this model, e.g. qwen2")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama HTTP base URL")
    parser.add_argument("--llm-planner-retries", type=int, default=DEFAULT_LLM_PLANNER_RETRIES)
    parser.add_argument("--json", action="store_true", help="Print compact JSON only")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    task = _normalize_text(args.task)
    task_from_file = _read_task_from_file(args.task_file) if args.task_file else ""
    if task_from_file:
        task = task_from_file

    try:
        result = run_self_edit_loop(
            task,
            repo_root=args.repo_root,
            verify_commands=args.verify,
            max_attempts=args.max_attempts,
            allow_core=args.allow_core,
            verify_timeout_seconds=args.verify_timeout,
            planner_mode=args.planner,
            llm_planner_command=args.llm_planner_command,
            llm_planner_timeout=args.llm_planner_timeout,
            ollama_model=args.ollama_model,
            ollama_url=args.ollama_url,
            llm_planner_retries=args.llm_planner_retries,
        )
    except SelfEditSafetyError as exc:
        payload = {
            "ok": False,
            "status": "blocked",
            "reason": str(exc),
            "code_chain_version": CODE_CHAIN_VERSION,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "code_chain_version": CODE_CHAIN_VERSION,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    data = result.to_dict()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
