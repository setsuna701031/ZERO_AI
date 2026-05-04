#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO Z+++++ - Classifier Strategy Registry Executor

Place this file at:
    E:\zero_ai\persona_workcopy_executor.py

Purpose:
- Read the latest Persona command.
- Build a deterministic edit plan.
- Edit only workspace/self_edit/zero_ai_workcopy.
- Validate Python files with ast.parse and py_compile.
- Trigger explicit fault injection only when requested.
- Run strategy-based retry repair.
- Fall back to rebuilding the generated status bridge if strategy repair fails.
- Generate review artifacts.
- Never apply back automatically.

Commands:
    python persona_workcopy_executor.py run
    python persona_workcopy_executor.py status
    python persona_workcopy_executor.py inspect
    python persona_workcopy_executor.py plan
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SELF_EDIT_ROOT = Path("workspace") / "self_edit"
WORKCOPY_DIR = SELF_EDIT_ROOT / "zero_ai_workcopy"
REVIEW_DIR = SELF_EDIT_ROOT / "review"

PERSONA_INBOX = SELF_EDIT_ROOT / "persona_inbox"
PERSONA_OUTBOX = SELF_EDIT_ROOT / "persona_outbox"
LATEST_COMMAND_TXT = PERSONA_INBOX / "latest_command.txt"
PERSONA_REPLY_TXT = PERSONA_OUTBOX / "persona_reply.txt"

EXECUTION_ROOT = SELF_EDIT_ROOT / "persona_execution"
EXECUTION_LOG_JSONL = EXECUTION_ROOT / "execution_log.jsonl"
EXECUTION_STATUS_JSON = EXECUTION_ROOT / "execution_status.json"
EXECUTION_STATUS_TXT = EXECUTION_ROOT / "execution_status.txt"
EXECUTION_PLAN_JSON = EXECUTION_ROOT / "execution_plan.json"
EXECUTION_PLAN_TXT = EXECUTION_ROOT / "execution_plan.txt"
RETRY_LOG_JSON = EXECUTION_ROOT / "retry_log.json"

REPORT_FILE = WORKCOPY_DIR / "Z5_CLASSIFIER_STRATEGY_REGISTRY_REPORT.md"

CHANGED_FILES_TXT = REVIEW_DIR / "changed_files.txt"
DIFF_TXT = REVIEW_DIR / "diff.txt"
MANIFEST_JSON = REVIEW_DIR / "manifest.json"
DIFF_SUMMARY_JSON = REVIEW_DIR / "diff_summary.json"

MAX_RETRY = 4


HIGH_RISK_TERMS = {
    "apply back",
    "apply-back",
    "套回",
    "覆蓋本體",
    "刪除本體",
    "delete live",
    "remove live",
    "force push",
    "merge",
    "deploy",
    "token",
    "secret",
    "password",
    "format",
    "rmdir",
    "rm ",
}

WORKCOPY_BOUNDARY_TERMS = {
    "workcopy",
    "self_edit",
    "只修改",
    "不要 apply",
    "不要套回",
    "不要覆蓋本體",
}

STATUS_TERMS = {
    "status",
    "persona_status",
    "persona_status_bridge",
    "狀態",
    "顯示",
    "顯示流程",
    "bridge",
    "review",
    "回報",
}

CONSOLE_TERMS = {
    "console",
    "command",
    "ask",
    "execute",
    "指令",
    "入口",
    "persona_command",
}

EXECUTOR_TERMS = {
    "executor",
    "執行器",
    "修改",
    "patch",
    "code",
    "codex",
    "檔案",
    "planner",
    "plan",
    "retry",
    "修復",
}

DOC_TERMS = {
    "readme",
    "doc",
    "文件",
    "說明",
    "report",
    "demo",
}

FAULT_INJECTION_TERMS = {
    "測試 retry",
    "故意產生語法錯誤",
    "fault injection",
    "inject fault",
    "syntax error test",
}


@dataclass
class PlannedTask:
    action: str
    path: Path
    intent: str
    required: bool = True


@dataclass
class EditOperation:
    path: Path
    action: str
    reason: str
    before_exists: bool
    after_exists: bool = False
    validation: Optional[Dict[str, Any]] = None
    retries: int = 0


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    PERSONA_INBOX.mkdir(parents=True, exist_ok=True)
    PERSONA_OUTBOX.mkdir(parents=True, exist_ok=True)
    EXECUTION_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"[read failed] {path}: {type(exc).__name__}: {exc}"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_latest_command() -> str:
    text = read_text(LATEST_COMMAND_TXT).strip()
    if not text:
        raise SystemExit("No latest Persona command found. Run persona_command_console.py ask first.")
    return text


def command_matches(command: str, terms: set[str]) -> bool:
    lower = command.lower()
    return any(term.lower() in lower for term in terms)


def should_inject_fault(command: str) -> bool:
    return command_matches(command, FAULT_INJECTION_TERMS)


def classify_risk(command: str) -> str:
    lower = command.lower()
    for term in HIGH_RISK_TERMS:
        if term.lower() in lower:
            return "high"
    return "normal"


def workcopy_ready() -> bool:
    return WORKCOPY_DIR.exists() and WORKCOPY_DIR.is_dir()


def assert_inside_workcopy(path: Path) -> None:
    work = WORKCOPY_DIR.resolve()
    target = path.resolve()
    try:
        target.relative_to(work)
    except ValueError:
        raise SystemExit(f"Refusing path outside workcopy: {path}")


def run_review_generation() -> None:
    if not Path("self_edit_zero.py").exists():
        return
    subprocess.run(
        [sys.executable, "self_edit_zero.py", "package-review"],
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )


def run_py_compile(path: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        text=True,
        encoding="utf-8",
        errors="ignore",
        capture_output=True,
        check=False,
    )
    return {
        "command": f"{sys.executable} -m py_compile {path}",
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "ok": proc.returncode == 0,
    }


def validate_python_source(path: Path) -> Dict[str, Any]:
    assert_inside_workcopy(path)
    source = read_text(path)
    try:
        ast.parse(source)
        ast_ok = True
        ast_error = ""
        ast_lineno = None
    except SyntaxError as exc:
        ast_ok = False
        ast_error = str(exc)
        ast_lineno = exc.lineno

    compile_result = run_py_compile(path)
    return {
        "path": str(path),
        "ast_ok": ast_ok,
        "ast_error": ast_error,
        "ast_lineno": ast_lineno,
        "py_compile": compile_result,
        "ok": ast_ok and compile_result["ok"],
    }


def parse_compile_line(validation: Dict[str, Any]) -> Optional[int]:
    line = validation.get("ast_lineno")
    if isinstance(line, int):
        return line

    stderr = ((validation.get("py_compile") or {}).get("stderr") or "")
    match = re.search(r"line\s+(\d+)", stderr)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def classify_validation_error(validation: Dict[str, Any]) -> str:
    text = (
        str(validation.get("ast_error", ""))
        + "\n"
        + str((validation.get("py_compile") or {}).get("stderr", ""))
    ).lower()

    if "unexpected character after line continuation" in text:
        return "line_continuation"
    if "unterminated string" in text or "eol while scanning string" in text:
        return "unterminated_string"
    if "expected an indented block" in text or "indentationerror" in text:
        return "indentation"
    if "was never closed" in text or "closing parenthesis" in text:
        return "unclosed_delimiter"
    if "invalid decimal literal" in text:
        return "invalid_token"
    if "invalid syntax" in text:
        return "invalid_syntax"
    if "modulenotfounderror" in text or "importerror" in text:
        return "import_error"
    if "nameerror" in text:
        return "name_error"
    if "attributeerror" in text:
        return "attribute_error"
    return "unknown"


def repair_strategy_normalize_escapes(source: str) -> tuple[str, List[str]]:
    fixed = source.replace(chr(92) + chr(34) * 3, chr(34) * 3)
    fixed = fixed.replace(chr(92) + chr(39) * 3, chr(39) * 3)
    if fixed != source:
        return fixed, ["normalize_escapes"]
    return source, []


def repair_strategy_remove_lonely_backslash(source: str) -> tuple[str, List[str]]:
    lines = source.splitlines()
    changed = False
    new_lines: List[str] = []

    for line in lines:
        if line.strip() == "\\":
            new_lines.append("# ZERO Z5 removed injected lonely backslash")
            changed = True
        else:
            new_lines.append(line)

    if changed:
        return "\n".join(new_lines) + ("\n" if source.endswith("\n") else ""), ["remove_lonely_backslash"]
    return source, []


def repair_strategy_comment_failing_line(source: str, validation: Dict[str, Any]) -> tuple[str, List[str]]:
    line_no = parse_compile_line(validation)
    if line_no is None:
        return source, []

    lines = source.splitlines()
    idx = line_no - 1
    if 0 <= idx < len(lines):
        lines[idx] = "# ZERO Z5 commented invalid line: " + lines[idx]
        return "\n".join(lines) + ("\n" if source.endswith("\n") else ""), [f"comment_failing_line:{line_no}"]

    return source, []


def apply_repair_strategy(path: Path, validation: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    assert_inside_workcopy(path)
    before = read_text(path)
    after = before
    actions: List[str] = []

    if strategy == "normalize_escapes":
        after, actions = repair_strategy_normalize_escapes(before)
    elif strategy == "remove_lonely_backslash":
        after, actions = repair_strategy_remove_lonely_backslash(before)
    elif strategy == "comment_failing_line":
        after, actions = repair_strategy_comment_failing_line(before, validation)
    elif strategy == "fallback_rebuild_status_bridge" and path.name == "persona_status_bridge.py":
        after = make_status_bridge_source()
        actions = ["fallback_rebuild_status_bridge"]
    else:
        actions = [f"strategy_skipped:{strategy}"]

    if after != before:
        write_text(path, after)

    after_validation = validate_python_source(path)
    return {
        "path": str(path),
        "strategy": strategy,
        "error_class": classify_validation_error(validation),
        "actions": actions,
        "before_ok": validation.get("ok"),
        "after_ok": after_validation.get("ok"),
        "after_validation": after_validation,
    }


def choose_repair_strategies(validation: Dict[str, Any], path: Path) -> List[str]:
    error_class = classify_validation_error(validation)

    fallback = ["fallback_rebuild_status_bridge"] if path.name == "persona_status_bridge.py" else []

    if error_class == "line_continuation":
        return ["remove_lonely_backslash", "comment_failing_line", "normalize_escapes"] + fallback
    if error_class == "unterminated_string":
        return ["comment_failing_line", "normalize_escapes"] + fallback
    if error_class == "indentation":
        return ["comment_failing_line"] + fallback
    if error_class == "invalid_syntax":
        return ["comment_failing_line", "remove_lonely_backslash", "normalize_escapes"] + fallback

    return ["normalize_escapes", "remove_lonely_backslash", "comment_failing_line"] + fallback


def validate_and_retry(ops: List[EditOperation]) -> Dict[str, Any]:
    retry_records: List[Dict[str, Any]] = []
    final_validations: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for op in ops:
        path = op.path
        key = str(path)
        if key in seen:
            continue
        seen.add(key)

        assert_inside_workcopy(path)
        if path.suffix.lower() != ".py" or not path.exists():
            validation = {"path": str(path), "ok": True, "note": "non-python file"}
            op.validation = validation
            final_validations.append(validation)
            continue

        validation = validate_python_source(path)
        attempts = 0
        used: set[str] = set()

        while not validation.get("ok") and attempts < MAX_RETRY:
            strategy = None
            for candidate in choose_repair_strategies(validation, path):
                if candidate not in used:
                    strategy = candidate
                    break

            if strategy is None:
                strategy = "comment_failing_line"

            used.add(strategy)
            repair = apply_repair_strategy(path, validation, strategy)
            attempts += 1
            op.retries = attempts
            retry_records.append(
                {
                    "path": str(path),
                    "attempt": attempts,
                    "strategy": strategy,
                    "error_class": classify_validation_error(validation),
                    "repair": repair,
                }
            )
            validation = repair["after_validation"]

        if not validation.get("ok") and path.name == "persona_status_bridge.py":
            repair = apply_repair_strategy(path, validation, "fallback_rebuild_status_bridge")
            attempts += 1
            op.retries = attempts
            retry_records.append(
                {
                    "path": str(path),
                    "attempt": attempts,
                    "strategy": "fallback_rebuild_status_bridge",
                    "error_class": classify_validation_error(validation),
                    "repair": repair,
                }
            )
            validation = repair["after_validation"]

        op.validation = validation
        final_validations.append(validation)

    write_text(
        RETRY_LOG_JSON,
        json.dumps(
            {
                "generated_at": now(),
                "max_retry": MAX_RETRY,
                "retry_count": len(retry_records),
                "strategy_retry": True,
                "records": retry_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    return {
        "validations": final_validations,
        "retry_records": retry_records,
        "failed": [v for v in final_validations if not v.get("ok")],
    }


def find_existing_workcopy_file(name: str) -> Optional[Path]:
    direct = WORKCOPY_DIR / name
    if direct.exists():
        return direct

    matches = list(WORKCOPY_DIR.rglob(name))
    matches = [p for p in matches if ".git" not in p.parts and "__pycache__" not in p.parts]
    return matches[0] if matches else None


def make_status_bridge_source() -> str:
    return "\n".join(
        [
            "#!/usr/bin/env python3",
            "# -*- coding: utf-8 -*-",
            '"""',
            "Workcopy Persona Status Bridge",
            "",
            "Maintained by ZERO Z+++++ strategy-retry executor.",
            "Safe to review before apply-back.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "from typing import Any, Dict",
            "",
            "",
            'SELF_EDIT_ROOT = Path("workspace") / "self_edit"',
            'STATUS_JSON = SELF_EDIT_ROOT / "persona_status.json"',
            'REVIEW_DIR = SELF_EDIT_ROOT / "review"',
            'CHANGED_FILES_TXT = REVIEW_DIR / "changed_files.txt"',
            'DIFF_SUMMARY_JSON = REVIEW_DIR / "diff_summary.json"',
            'MANIFEST_JSON = REVIEW_DIR / "manifest.json"',
            "",
            "",
            "def read_json(path: Path) -> Dict[str, Any]:",
            "    if not path.exists():",
            "        return {}",
            "    try:",
            '        return json.loads(path.read_text(encoding="utf-8"))',
            "    except Exception as exc:",
            '        return {"error": type(exc).__name__ + ": " + str(exc)}',
            "",
            "",
            "def read_lines(path: Path) -> list[str]:",
            "    if not path.exists():",
            "        return []",
            "    try:",
            '        return path.read_text(encoding="utf-8").splitlines()',
            "    except Exception:",
            "        return []",
            "",
            "",
            "def build_status_summary() -> Dict[str, Any]:",
            "    status = read_json(STATUS_JSON)",
            "    diff_summary = read_json(DIFF_SUMMARY_JSON)",
            "    manifest = read_json(MANIFEST_JSON)",
            "    changed = read_lines(CHANGED_FILES_TXT)",
            "",
            "    return {",
            '        "phase": status.get("phase"),',
            '        "summary": status.get("summary"),',
            '        "changed_file_count": diff_summary.get("changed_file_count", len(changed)),',
            '        "added": diff_summary.get("added", 0),',
            '        "modified": diff_summary.get("modified", 0),',
            '        "deleted": diff_summary.get("deleted", 0),',
            '        "changed_files": changed,',
            '        "manifest_file_count": len(manifest.get("files", [])) if isinstance(manifest.get("files"), list) else 0,',
            '        "human_review_required": True,',
            '        "apply_back_allowed": False,',
            '        "executor_package": "Z+++++",',
            "    }",
            "",
            "",
            "def format_status_summary(summary: Dict[str, Any]) -> str:",
            "    lines = [",
            '        "[ZERO WORKCOPY PERSONA STATUS]",',
            '        "Phase              : " + str(summary.get("phase")),',
            '        "Summary            : " + str(summary.get("summary")),',
            '        "Changed file count : " + str(summary.get("changed_file_count")),',
            '        "Added              : " + str(summary.get("added")),',
            '        "Modified           : " + str(summary.get("modified")),',
            '        "Deleted            : " + str(summary.get("deleted")),',
            '        "Manifest files     : " + str(summary.get("manifest_file_count")),',
            '        "Human review needed: True",',
            '        "Apply back allowed : False",',
            '        "Executor package   : Z+++++",',
            '        "",',
            '        "[CHANGED FILES]",',
            "    ]",
            "",
            '    files = summary.get("changed_files") or []',
            "    if files:",
            "        for item in files:",
            '            lines.append("- " + str(item))',
            "    else:",
            '        lines.append("(none)")',
            "",
            '    return "\\n".join(lines) + "\\n"',
            "",
            "",
            "def z5_classifier_strategy_marker() -> dict[str, str]:",
            "    return {",
            '        "package": "Z+++++",',
            '        "mode": "classifier_strategy_registry_code_edit",',
            '        "boundary": "workcopy_only",',
            '        "apply_back": "manual_review_required",',
            "    }",
            "",
            "",
            "def main() -> int:",
            "    print(format_status_summary(build_status_summary()))",
            "    return 0",
            "",
            "",
            'if __name__ == "__main__":',
            "    raise SystemExit(main())",
            "",
        ]
    )


def build_plan(command: str) -> Dict[str, Any]:
    risk = classify_risk(command)
    allow_workcopy_only = risk != "high" or command_matches(command, WORKCOPY_BOUNDARY_TERMS)

    tasks: List[PlannedTask] = []
    if allow_workcopy_only:
        if command_matches(command, STATUS_TERMS) or should_inject_fault(command):
            tasks.append(
                PlannedTask(
                    action="replace_status_bridge",
                    path=WORKCOPY_DIR / "persona_status_bridge.py",
                    intent="Improve Persona status/review display bridge.",
                )
            )

        if command_matches(command, CONSOLE_TERMS):
            console = find_existing_workcopy_file("persona_command_console.py")
            if console:
                tasks.append(
                    PlannedTask(
                        action="append_python_marker",
                        path=console,
                        intent="Mark command console as observed by Z5 planner.",
                        required=False,
                    )
                )

        if command_matches(command, EXECUTOR_TERMS):
            executor = find_existing_workcopy_file("persona_workcopy_executor.py")
            if executor:
                tasks.append(
                    PlannedTask(
                        action="append_python_marker",
                        path=executor,
                        intent="Mark executor as selected by Z5 planner.",
                        required=False,
                    )
                )

        if command_matches(command, DOC_TERMS):
            readme = find_existing_workcopy_file("README.md")
            if readme:
                tasks.append(
                    PlannedTask(
                        action="append_text_marker",
                        path=readme,
                        intent="Add Z5 controlled edit documentation marker.",
                        required=False,
                    )
                )

        if not tasks:
            tasks.append(
                PlannedTask(
                    action="write_report_only",
                    path=REPORT_FILE,
                    intent="No safe code target selected; write report only.",
                    required=True,
                )
            )

    for task in tasks:
        assert_inside_workcopy(task.path)

    return {
        "generated_at": now(),
        "package": "Z+++++",
        "risk": risk,
        "allow_workcopy_only": allow_workcopy_only,
        "mode": "classifier_strategy_registry_code_edit" if allow_workcopy_only else "blocked",
        "command": command,
        "fault_injection": {"enabled": should_inject_fault(command), "trigger": "explicit user command only"},
        "retry": {"enabled": True, "max_retry": MAX_RETRY, "strategy_retry": True},
        "tasks": [
            {"action": task.action, "path": str(task.path), "intent": task.intent, "required": task.required}
            for task in tasks
        ],
        "boundary": {
            "live_repo_write_allowed": False,
            "workcopy_write_allowed": True,
            "apply_back_requires_human_review": True,
        },
    }


def save_plan(plan: Dict[str, Any]) -> None:
    write_text(EXECUTION_PLAN_JSON, json.dumps(plan, ensure_ascii=False, indent=2))

    lines = [
        "[ZERO Z+++++ EXECUTION PLAN]",
        "Time   : " + str(plan.get("generated_at")),
        "Risk   : " + str(plan.get("risk")),
        "Mode   : " + str(plan.get("mode")),
        "Fault  : " + str((plan.get("fault_injection") or {}).get("enabled")),
        "Retry  : strategy, max=" + str(MAX_RETRY),
        "",
        "[TASKS]",
    ]

    tasks = plan.get("tasks") or []
    if tasks:
        for item in tasks:
            lines.append(
                "- " + str(item.get("action")) + " | " + str(item.get("path")) + " | " + str(item.get("intent"))
            )
    else:
        lines.append("(none)")

    lines.extend(
        [
            "",
            "[BOUNDARY]",
            "Live repo write allowed : False",
            "Workcopy write allowed  : True",
            "Review before apply     : True",
        ]
    )

    write_text(EXECUTION_PLAN_TXT, "\n".join(lines) + "\n")


def replace_status_bridge(path: Path, command: str) -> EditOperation:
    assert_inside_workcopy(path)
    before_exists = path.exists()

    content = make_status_bridge_source()
    injected = False
    if should_inject_fault(command):
        content = content.rstrip() + "\n\\\n"
        injected = True

    write_text(path, content)

    reason = "Planner task replace_status_bridge"
    if injected:
        reason += " with intentional syntax fault for classifier strategy retry validation"

    return EditOperation(
        path=path,
        action="updated" if before_exists else "created",
        reason=reason,
        before_exists=before_exists,
        after_exists=True,
    )


def append_python_marker(path: Path, command: str) -> EditOperation:
    assert_inside_workcopy(path)
    before_exists = path.exists()
    source = read_text(path)

    marker_name = "z5_classifier_strategy_marker"
    if marker_name in source:
        return EditOperation(
            path=path,
            action="unchanged",
            reason="Z5 marker already exists",
            before_exists=before_exists,
            after_exists=path.exists(),
        )

    command_json = json.dumps(command, ensure_ascii=False)
    block = (
        "\n\n\n# --- ZERO Z+++++ classifier strategy retry marker ---\n"
        f"def {marker_name}() -> dict[str, str]:\n"
        "    return {\n"
        '        "package": "Z+++++",\n'
        '        "mode": "classifier_strategy_registry_code_edit",\n'
        '        "boundary": "workcopy_only",\n'
        f'        "last_command": {command_json},\n'
        "    }\n"
    )

    write_text(path, source.rstrip() + block)
    return EditOperation(
        path=path,
        action="patched" if before_exists else "created",
        reason="Planner task append_python_marker",
        before_exists=before_exists,
        after_exists=True,
    )


def append_text_marker(path: Path, command: str) -> EditOperation:
    assert_inside_workcopy(path)
    before_exists = path.exists()
    source = read_text(path)
    marker = "<!-- ZERO_Z5_CLASSIFIER_STRATEGY_MARKER -->"

    if marker in source:
        return EditOperation(
            path=path,
            action="unchanged",
            reason="Z5 text marker already exists",
            before_exists=before_exists,
            after_exists=path.exists(),
        )

    block = (
        "\n\n"
        "<!-- ZERO_Z5_CLASSIFIER_STRATEGY_MARKER -->\n"
        "## ZERO Z+++++ Controlled Edit\n\n"
        "- Mode: strategy-retry workcopy edit\n"
        "- Boundary: workcopy only\n"
        "- Apply-back: manual review required\n"
        "- Max retry: `" + str(MAX_RETRY) + "`\n"
        "- Command: `" + command.replace("`", "'") + "`\n"
    )

    write_text(path, source.rstrip() + block + "\n")
    return EditOperation(
        path=path,
        action="patched" if before_exists else "created",
        reason="Planner task append_text_marker",
        before_exists=before_exists,
        after_exists=True,
    )


def execute_task(task: Dict[str, Any], command: str) -> EditOperation:
    action = str(task.get("action"))
    path = Path(str(task.get("path")))
    assert_inside_workcopy(path)

    if action == "replace_status_bridge":
        return replace_status_bridge(path, command)
    if action == "append_python_marker":
        return append_python_marker(path, command)
    if action == "append_text_marker":
        return append_text_marker(path, command)
    if action == "write_report_only":
        return EditOperation(
            path=path,
            action="deferred",
            reason="Report-only task; report written after validation phase",
            before_exists=path.exists(),
            after_exists=path.exists(),
        )

    raise SystemExit(f"Unknown planned action: {action}")


def write_report(command: str, plan: Dict[str, Any], ops: List[EditOperation], validation_bundle: Dict[str, Any]) -> EditOperation:
    assert_inside_workcopy(REPORT_FILE)
    before_exists = REPORT_FILE.exists()

    validations = validation_bundle.get("validations", [])
    retries = validation_bundle.get("retry_records", [])
    failed = validation_bundle.get("failed", [])

    lines = [
        "# ZERO Z+++++ Strategy Retry Report",
        "",
        "Generated at: " + now(),
        "",
        "## Command",
        "",
        "```text",
        command,
        "```",
        "",
        "## Plan",
        "",
        "- Risk: `" + str(plan.get("risk")) + "`",
        "- Mode: `" + str(plan.get("mode")) + "`",
        "- Workcopy only: `True`",
        "- Apply-back: `manual review required`",
        "- Fault injection: `" + str((plan.get("fault_injection") or {}).get("enabled")) + "`",
        "- Classifier classifier strategy retry enabled: `True`",
        "- Max retry: `" + str(MAX_RETRY) + "`",
        "",
        "## Tasks",
        "",
    ]

    for item in plan.get("tasks", []):
        lines.append(
            "- `" + str(item.get("action")) + "` | `" + str(item.get("path")) + "` | " + str(item.get("intent"))
        )

    lines.extend(["", "## Operations", ""])
    if ops:
        for op in ops:
            lines.append("- `" + str(op.path) + "` | " + op.action + " | retries=" + str(op.retries) + " | " + op.reason)
    else:
        lines.append("- none")

    lines.extend(["", "## Validation", ""])
    if validations:
        for item in validations:
            lines.append("- `" + str(item.get("path")) + "` | ok=`" + str(item.get("ok")) + "`")
    else:
        lines.append("- none")

    lines.extend(["", "## Strategy Retry / Fallback Records", ""])
    if retries:
        for item in retries:
            lines.append(
                "- `" + str(item.get("path")) + "` | attempt=`" + str(item.get("attempt")) + "` | strategy=`" + str(item.get("strategy")) + "` | error_class=`" + str(item.get("error_class")) + "`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Failed Validations", ""])
    if failed:
        for item in failed:
            lines.append("- `" + str(item.get("path")) + "` | error=`" + str(item.get("ast_error")) + "`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Gate",
            "",
            "Apply-back is blocked until:",
            "",
            "```bat",
            "python self_edit_apply_back.py --confirm-reviewed",
            "```",
        ]
    )

    write_text(REPORT_FILE, "\n".join(lines) + "\n")

    return EditOperation(
        path=REPORT_FILE,
        action="updated" if before_exists else "created",
        reason="Wrote Z+++++ classifier strategy retry report",
        before_exists=before_exists,
        after_exists=True,
    )


def execute_plan(command: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    if not plan.get("allow_workcopy_only"):
        return {
            "generated_at": now(),
            "status": "blocked",
            "risk": plan.get("risk"),
            "command": command,
            "reason": "High-risk command without explicit workcopy-only boundary.",
            "plan": plan,
        }

    ops: List[EditOperation] = []
    for task in plan.get("tasks", []):
        op = execute_task(task, command)
        if op.action != "deferred":
            ops.append(op)

    validation_bundle = validate_and_retry(ops)
    report_op = write_report(command, plan, ops, validation_bundle)
    ops.append(report_op)

    failed = validation_bundle.get("failed", [])

    return {
        "generated_at": now(),
        "status": "failed_validation" if failed else "finished",
        "risk": plan.get("risk"),
        "mode": plan.get("mode"),
        "command": command,
        "plan": plan,
        "operations": [
            {
                "path": str(op.path),
                "action": op.action,
                "reason": op.reason,
                "before_exists": op.before_exists,
                "after_exists": op.after_exists,
                "validation": op.validation,
                "retries": op.retries,
            }
            for op in ops
        ],
        "validations": validation_bundle.get("validations", []),
        "retry_records": validation_bundle.get("retry_records", []),
        "failed_validations": failed,
        "retry_log": str(RETRY_LOG_JSON),
        "report": str(REPORT_FILE),
        "boundary": {
            "live_repo_write_allowed": False,
            "workcopy_write_allowed": True,
            "apply_back_requires_human_review": True,
        },
    }


def format_execution_status(result: Dict[str, Any]) -> str:
    lines = [
        "[ZERO Z+++++ EXECUTION STATUS]",
        "Time   : " + str(result.get("generated_at")),
        "Status : " + str(result.get("status")),
        "Risk   : " + str(result.get("risk")),
        "Mode   : " + str(result.get("mode")),
        "",
        "[COMMAND]",
        str(result.get("command", "")),
        "",
    ]

    if result.get("status") == "blocked":
        lines.extend(["[BLOCKED]", str(result.get("reason", "")), ""])
    else:
        lines.append("[OPERATIONS]")
        operations = result.get("operations") or []
        if operations:
            for op in operations:
                lines.append(
                    "- "
                    + str(op.get("action"))
                    + ": "
                    + str(op.get("path"))
                    + " | retries="
                    + str(op.get("retries", 0))
                    + " | "
                    + str(op.get("reason"))
                )
        else:
            lines.append("- none")

        lines.extend(["", "[VALIDATION]"])
        validations = result.get("validations") or []
        if validations:
            for item in validations:
                lines.append("- " + str(item.get("path")) + " | ok=" + str(item.get("ok")))
        else:
            lines.append("- none")

        lines.extend(["", "[CLASSIFIER STRATEGY RETRY]"])
        retries = result.get("retry_records") or []
        if retries:
            for item in retries:
                lines.append(
                    "- "
                    + str(item.get("path"))
                    + " | attempt="
                    + str(item.get("attempt"))
                    + " | strategy="
                    + str(item.get("strategy"))
                    + " | error_class="
                    + str(item.get("error_class"))
                )
        else:
            lines.append("- none")

        lines.extend(
            [
                "",
                "[REVIEW]",
                "Changed files : " + str(CHANGED_FILES_TXT),
                "Diff          : " + str(DIFF_TXT),
                "Manifest      : " + str(MANIFEST_JSON),
                "Diff summary  : " + str(DIFF_SUMMARY_JSON),
                "Plan          : " + str(EXECUTION_PLAN_JSON),
                "Retry log     : " + str(RETRY_LOG_JSON),
                "Report        : " + str(result.get("report", "")),
            ]
        )

    lines.extend(["", "[GATE]", "Apply back is still manual:", "python self_edit_apply_back.py --confirm-reviewed"])
    return "\n".join(lines) + "\n"


def format_persona_reply(result: Dict[str, Any]) -> str:
    if result.get("status") == "blocked":
        return (
            "\n".join(
                [
                    "[ZERO PERSONA REPLY]",
                    "Result : blocked",
                    "Reason : " + str(result.get("reason")),
                    "",
                    "No workcopy edit was performed.",
                ]
            )
            + "\n"
        )

    return (
        "\n".join(
            [
                "[ZERO PERSONA REPLY]",
                "Result : " + str(result.get("status")),
                "Mode   : " + str(result.get("mode")),
                "Report : " + str(result.get("report")),
                "",
                "ZERO Z+++++ classifier strategy retry executor performed controlled workcopy edits.",
                "Review artifacts were generated.",
                "",
                "Next:",
                "python persona_command_console.py review",
            ]
        )
        + "\n"
    )


def execute_command(command: str) -> Dict[str, Any]:
    ensure_dirs()

    if not workcopy_ready():
        raise SystemExit("Workcopy missing. Run: python self_edit_zero.py prepare")

    plan = build_plan(command)
    save_plan(plan)

    result = execute_plan(command, plan)

    append_jsonl(EXECUTION_LOG_JSONL, result)
    write_text(EXECUTION_STATUS_JSON, json.dumps(result, ensure_ascii=False, indent=2))
    write_text(EXECUTION_STATUS_TXT, format_execution_status(result))
    write_text(PERSONA_REPLY_TXT, format_persona_reply(result))

    run_review_generation()
    return result


def print_status() -> None:
    ensure_dirs()
    print(read_text(EXECUTION_STATUS_TXT, "[ZERO Z+++++] No execution status yet."))


def print_inspect() -> None:
    ensure_dirs()
    if REPORT_FILE.exists():
        print(read_text(REPORT_FILE))
    else:
        print("[ZERO Z+++++] No report yet.")


def print_plan() -> None:
    ensure_dirs()
    print(read_text(EXECUTION_PLAN_TXT, "[ZERO Z+++++] No execution plan yet."))


def main() -> int:
    parser = argparse.ArgumentParser(description="ZERO Z+++++ Strategy Retry Executor")
    parser.add_argument("command", choices=["run", "status", "inspect", "plan"])
    args = parser.parse_args()

    if args.command == "run":
        command_text = load_latest_command()
        result = execute_command(command_text)
        print(format_execution_status(result))
        print("")
        print("[NEXT]")
        print("python persona_command_console.py review")
        return 0

    if args.command == "status":
        print_status()
        return 0

    if args.command == "inspect":
        print_inspect()
        return 0

    if args.command == "plan":
        print_plan()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
