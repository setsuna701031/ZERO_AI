from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "app.py"
WORKSPACE_DIR = REPO_ROOT / "workspace"
SHARED_DIR = WORKSPACE_DIR / "shared"

DEFAULT_INPUT_PATH = SHARED_DIR / "persona_agent_input.txt"
DEFAULT_SUMMARY_OUTPUT_PATH = SHARED_DIR / "persona_agent_summary.txt"
DEFAULT_ACTION_ITEMS_OUTPUT_PATH = SHARED_DIR / "persona_agent_action_items.txt"

DEFAULT_AGENT_GOAL = (
    "Read persona_agent_input.txt, then produce both a concise summary and action items."
)

DEFAULT_INPUT_TEXT = """Project Sync Notes

Alice will finish the API draft by Friday.
Bob will test the upload flow next week.
Carol will prepare a short release note before the internal demo.
The team agreed to keep the first demo focused on document processing and task lifecycle proof.
The next engineering priority is to connect persona runtime commands to official task execution paths.
"""


@dataclass
class CommandResult:
    label: str
    args: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class AgentTaskResult:
    label: str
    task_id: str
    create_result: CommandResult
    run_result: CommandResult
    result_result: CommandResult
    output_path: Path


@dataclass
class PersonaAgentDemoResult:
    ok: bool
    goal: str
    selected_plan: str
    summary_task: Optional[AgentTaskResult]
    action_items_task: Optional[AgentTaskResult]
    artifacts: List[Path]
    error: str = ""


def _safe_print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sanitized = str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(sanitized)


def _to_repo_relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _to_shared_relative(path: Path) -> str:
    try:
        return path.relative_to(SHARED_DIR).as_posix()
    except ValueError:
        return path.name


def _decode_process_text(data: bytes) -> str:
    if not data:
        return ""

    candidates = [
        "utf-8",
        "cp950",
        "cp936",
        "cp1252",
    ]

    for encoding in candidates:
        try:
            return data.decode(encoding)
        except Exception:
            pass

    return data.decode("utf-8", errors="replace")


def _run_app_command(label: str, *args: str) -> CommandResult:
    command = [sys.executable, str(APP_PATH), *args]

    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=False,
    )

    return CommandResult(
        label=label,
        args=command,
        returncode=result.returncode,
        stdout=_decode_process_text(result.stdout or b""),
        stderr=_decode_process_text(result.stderr or b""),
    )


def _extract_task_id(text: str) -> str:
    match = re.search(r"task_[0-9]+", text or "")
    return match.group(0) if match else ""


def _require_app_path() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"app.py not found: {APP_PATH}")


def _prepare_demo_input(input_path: Path = DEFAULT_INPUT_PATH) -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    input_path.write_text(DEFAULT_INPUT_TEXT, encoding="utf-8")


def classify_goal(goal: str) -> str:
    """
    Deterministic first-pass classifier.

    This intentionally avoids free LLM routing for now. The purpose of this file is
    to create a stable agent-level orchestration POC before introducing broader
    tool-choice autonomy.
    """
    lowered = (goal or "").strip().lower()

    wants_summary = any(word in lowered for word in ("summary", "summarize", "summarise", "摘要"))
    wants_action_items = any(
        word in lowered
        for word in (
            "action item",
            "action items",
            "todo",
            "tasks",
            "待辦",
            "行動項目",
        )
    )
    document_hint = any(
        word in lowered
        for word in (
            "read",
            "document",
            "file",
            "notes",
            "input",
            "txt",
            "文件",
            "讀",
        )
    )

    if document_hint and wants_summary and wants_action_items:
        return "document_summary_and_action_items"

    if wants_summary and wants_action_items:
        return "document_summary_and_action_items"

    return "unsupported"


def _validate_text_artifact(path: Path, label: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"{label} missing: {_to_repo_relative(path)}"

    if not path.is_file():
        return False, f"{label} is not a file: {_to_repo_relative(path)}"

    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return False, f"{label} cannot be read: {exc}"

    if not text:
        return False, f"{label} is empty: {_to_repo_relative(path)}"

    if "{{previous_result}}" in text or "{{file_content}}" in text:
        return False, f"{label} still contains unresolved template placeholder"

    return True, ""


def _run_document_task_lifecycle(
    label: str,
    create_args: List[str],
    output_path: Path,
) -> tuple[Optional[AgentTaskResult], Optional[str]]:
    create_result = _run_app_command(
        f"{label}: create task",
        *create_args,
    )

    if not create_result.ok:
        return None, (
            f"{label} create failed with code {create_result.returncode}\n"
            f"stdout:\n{create_result.stdout}\n"
            f"stderr:\n{create_result.stderr}"
        )

    task_id = _extract_task_id(create_result.stdout + "\n" + create_result.stderr)
    if not task_id:
        return None, (
            f"{label} create succeeded but no task_id was found\n"
            f"stdout:\n{create_result.stdout}\n"
            f"stderr:\n{create_result.stderr}"
        )

    run_result = _run_app_command(
        f"{label}: run task",
        "task",
        "run",
        task_id,
    )

    if not run_result.ok:
        return None, (
            f"{label} run failed with code {run_result.returncode}\n"
            f"task_id: {task_id}\n"
            f"stdout:\n{run_result.stdout}\n"
            f"stderr:\n{run_result.stderr}"
        )

    result_result = _run_app_command(
        f"{label}: read result",
        "task",
        "result",
        task_id,
    )

    if not result_result.ok:
        return None, (
            f"{label} result failed with code {result_result.returncode}\n"
            f"task_id: {task_id}\n"
            f"stdout:\n{result_result.stdout}\n"
            f"stderr:\n{result_result.stderr}"
        )

    artifact_ok, artifact_error = _validate_text_artifact(output_path, label)
    if not artifact_ok:
        return None, (
            f"{label} artifact validation failed\n"
            f"task_id: {task_id}\n"
            f"error: {artifact_error}\n"
            f"result stdout:\n{result_result.stdout}"
        )

    return (
        AgentTaskResult(
            label=label,
            task_id=task_id,
            create_result=create_result,
            run_result=run_result,
            result_result=result_result,
            output_path=output_path,
        ),
        None,
    )


def _print_command_block(result: CommandResult, include_full_stdout: bool = False) -> None:
    _safe_print(f"[agent-demo] {result.label}")
    _safe_print(f"returncode: {result.returncode}")

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if stdout:
        if include_full_stdout:
            _safe_print("stdout:")
            _safe_print(stdout)
        else:
            lines = stdout.splitlines()
            preview = lines[-12:] if len(lines) > 12 else lines
            _safe_print("stdout_tail:")
            for line in preview:
                _safe_print(f"  {line}")

    if stderr:
        _safe_print("stderr:")
        _safe_print(stderr)


def _print_task_summary(task: AgentTaskResult) -> None:
    _safe_print(f"[agent-demo] {task.label}")
    _safe_print(f"task_id: {task.task_id}")
    _safe_print(f"artifact: {_to_repo_relative(task.output_path)}")
    _safe_print("")


def run_persona_agent_demo(goal: str = DEFAULT_AGENT_GOAL) -> int:
    """
    Run the first deterministic persona agent orchestration proof.

    This is intentionally more agent-like than the prior fixed multi-step demo:
    the function receives a goal, classifies it, selects the existing document
    task lifecycle path, runs multiple official tasks, validates artifacts, and
    returns a combined result.
    """
    result = run_persona_agent_demo_result(goal)
    print_persona_agent_demo_result(result)
    return 0 if result.ok else 1


def run_persona_agent_demo_result(goal: str = DEFAULT_AGENT_GOAL) -> PersonaAgentDemoResult:
    try:
        _require_app_path()
        _prepare_demo_input()
    except Exception as exc:
        return PersonaAgentDemoResult(
            ok=False,
            goal=goal,
            selected_plan="startup_failed",
            summary_task=None,
            action_items_task=None,
            artifacts=[],
            error=str(exc),
        )

    selected_plan = classify_goal(goal)

    if selected_plan != "document_summary_and_action_items":
        return PersonaAgentDemoResult(
            ok=False,
            goal=goal,
            selected_plan=selected_plan,
            summary_task=None,
            action_items_task=None,
            artifacts=[],
            error=(
                "unsupported goal for deterministic persona agent POC. "
                "Try a goal that asks for both summary and action items."
            ),
        )

    summary_task, summary_error = _run_document_task_lifecycle(
        label="summary document task",
        create_args=[
            "task",
            "doc-summary",
            _to_shared_relative(DEFAULT_INPUT_PATH),
            _to_shared_relative(DEFAULT_SUMMARY_OUTPUT_PATH),
        ],
        output_path=DEFAULT_SUMMARY_OUTPUT_PATH,
    )
    if summary_error:
        return PersonaAgentDemoResult(
            ok=False,
            goal=goal,
            selected_plan=selected_plan,
            summary_task=summary_task,
            action_items_task=None,
            artifacts=[],
            error=summary_error,
        )

    action_items_task, action_items_error = _run_document_task_lifecycle(
        label="action-items document task",
        create_args=[
            "task",
            "doc-action-items",
            _to_shared_relative(DEFAULT_INPUT_PATH),
            _to_shared_relative(DEFAULT_ACTION_ITEMS_OUTPUT_PATH),
        ],
        output_path=DEFAULT_ACTION_ITEMS_OUTPUT_PATH,
    )
    if action_items_error:
        return PersonaAgentDemoResult(
            ok=False,
            goal=goal,
            selected_plan=selected_plan,
            summary_task=summary_task,
            action_items_task=action_items_task,
            artifacts=[DEFAULT_SUMMARY_OUTPUT_PATH] if summary_task else [],
            error=action_items_error,
        )

    artifacts = [
        DEFAULT_SUMMARY_OUTPUT_PATH,
        DEFAULT_ACTION_ITEMS_OUTPUT_PATH,
    ]

    return PersonaAgentDemoResult(
        ok=True,
        goal=goal,
        selected_plan=selected_plan,
        summary_task=summary_task,
        action_items_task=action_items_task,
        artifacts=artifacts,
        error="",
    )


def print_persona_agent_demo_result(result: PersonaAgentDemoResult) -> None:
    _safe_print("[agent-demo] goal")
    _safe_print(result.goal)
    _safe_print("")
    _safe_print("[agent-demo] classify goal")
    _safe_print(f"selected_plan: {result.selected_plan}")
    _safe_print("")

    if result.summary_task is not None:
        _print_task_summary(result.summary_task)

    if result.action_items_task is not None:
        _print_task_summary(result.action_items_task)

    if result.artifacts:
        _safe_print("[agent-demo] verified artifacts")
        for artifact in result.artifacts:
            _safe_print(f"- {_to_repo_relative(artifact)}")
        _safe_print("")

    if result.summary_task is not None and result.action_items_task is not None:
        _safe_print("[agent-demo] task lifecycle")
        _safe_print(f"summary_task_id: {result.summary_task.task_id}")
        _safe_print(f"action_items_task_id: {result.action_items_task.task_id}")
        _safe_print("")

    if result.ok:
        _safe_print("[agent-demo] PASS")
        return

    _safe_print("[agent-demo] FAIL")
    if result.error:
        _safe_print(result.error)


def main() -> int:
    goal = " ".join(sys.argv[1:]).strip() or DEFAULT_AGENT_GOAL
    return run_persona_agent_demo(goal)


if __name__ == "__main__":
    raise SystemExit(main())
