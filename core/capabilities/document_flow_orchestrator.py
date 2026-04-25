from __future__ import annotations

import json
import locale
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "app.py"
WORKSPACE_DIR = REPO_ROOT / "workspace"
SHARED_DIR = WORKSPACE_DIR / "shared"

DEFAULT_INPUT_PATH = SHARED_DIR / "document_flow_orchestrator_input.txt"
DEFAULT_SUMMARY_OUTPUT_PATH = SHARED_DIR / "document_flow_orchestrator_summary.txt"
DEFAULT_ACTION_ITEMS_OUTPUT_PATH = SHARED_DIR / "document_flow_orchestrator_action_items.txt"

DEFAULT_INPUT_TEXT = """Engineering Review Notes

Alice will finish the API draft by Friday.
Bob will test the upload flow next week.
Carol will prepare the release note before the internal demo.
The team agreed that the next milestone should focus on document flow reliability.
The operator needs a concise summary and a separate action-items file.
"""


@dataclass
class CommandResult:
    label: str
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class DocumentTaskResult:
    label: str
    task_id: str
    output_path: Path
    create_result: CommandResult
    submit_result: CommandResult
    run_result: CommandResult
    result_result: CommandResult


@dataclass
class DocumentFlowResult:
    ok: bool
    input_path: Path
    summary_task: Optional[DocumentTaskResult] = None
    action_items_task: Optional[DocumentTaskResult] = None
    error: str = ""

    @property
    def artifacts(self) -> list[Path]:
        items: list[Path] = []
        if self.summary_task is not None:
            items.append(self.summary_task.output_path)
        if self.action_items_task is not None:
            items.append(self.action_items_task.output_path)
        return items


def safe_print(text: str = "") -> None:
    value = str(text or "")
    try:
        print(value)
        return
    except UnicodeEncodeError:
        pass

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    sanitized = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(sanitized)


def _decode_bytes(data: bytes) -> str:
    if not data:
        return ""

    encoding_candidates = [
        "utf-8",
        locale.getpreferredencoding(False) or "",
        "cp950",
        "cp936",
        "cp1252",
    ]

    for enc in encoding_candidates:
        if not enc:
            continue
        try:
            return data.decode(enc)
        except Exception:
            pass

    return data.decode("utf-8", errors="replace")


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


def ensure_required_paths() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"app.py not found: {APP_PATH}")
    SHARED_DIR.mkdir(parents=True, exist_ok=True)


def write_default_input(path: Path = DEFAULT_INPUT_PATH) -> Path:
    ensure_required_paths()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_INPUT_TEXT, encoding="utf-8")
    return path


def extract_first_json_object(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    start = raw.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(raw)):
        ch = raw[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]

    return ""


def parse_task_id(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""

    json_text = extract_first_json_object(stripped)
    if json_text:
        try:
            payload = json.loads(json_text)
            task_id = str(
                payload.get("task_id")
                or payload.get("task_name")
                or payload.get("task", {}).get("task_id")
                or payload.get("task", {}).get("task_name")
                or ""
            ).strip()
            if task_id:
                return task_id
        except Exception:
            pass

    match = re.search(r"task_[0-9]+", stripped)
    if match:
        return match.group(0).strip()

    return ""


def run_app_command(label: str, *args: str) -> CommandResult:
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
        stdout=_decode_bytes(result.stdout or b""),
        stderr=_decode_bytes(result.stderr or b""),
    )


def validate_text_artifact(path: Path, label: str) -> tuple[bool, str]:
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

    forbidden_markers = [
        "{{previous_result}}",
        "{{file_content}}",
    ]

    for marker in forbidden_markers:
        if marker in text:
            return False, f"{label} contains unresolved marker {marker}: {_to_repo_relative(path)}"

    return True, ""


def run_document_task(
    *,
    label: str,
    command_name: str,
    input_path: Path,
    output_path: Path,
    max_runs: int = 10,
) -> DocumentTaskResult:
    ensure_required_paths()

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    if output_path.exists():
        output_path.unlink()

    create_result = run_app_command(
        f"{label}: create",
        "task",
        command_name,
        _to_shared_relative(input_path),
        _to_shared_relative(output_path),
    )

    if not create_result.ok:
        raise RuntimeError(
            f"{label} create failed with return code {create_result.returncode}\n"
            f"STDOUT:\n{create_result.stdout}\n\n"
            f"STDERR:\n{create_result.stderr}"
        )

    task_id = parse_task_id(create_result.stdout + "\n" + create_result.stderr)
    if not task_id:
        raise RuntimeError(
            f"{label} create succeeded but task id could not be parsed\n"
            f"STDOUT:\n{create_result.stdout}\n\n"
            f"STDERR:\n{create_result.stderr}"
        )

    submit_result = run_app_command(
        f"{label}: submit",
        "task",
        "submit",
        task_id,
    )

    if not submit_result.ok or '"ok": false' in submit_result.stdout.lower():
        raise RuntimeError(
            f"{label} submit failed for {task_id} with return code {submit_result.returncode}\n"
            f"STDOUT:\n{submit_result.stdout}\n\n"
            f"STDERR:\n{submit_result.stderr}"
        )

    last_run_result = run_app_command(
        f"{label}: run",
        "task",
        "run",
        task_id,
    )
    if not last_run_result.ok:
        raise RuntimeError(
            f"{label} run failed for {task_id} with return code {last_run_result.returncode}\n"
            f"STDOUT:\n{last_run_result.stdout}\n\n"
            f"STDERR:\n{last_run_result.stderr}"
        )

    result_result = run_app_command(
        f"{label}: result",
        "task",
        "result",
        task_id,
    )
    if not result_result.ok:
        raise RuntimeError(
            f"{label} result failed for {task_id} with return code {result_result.returncode}\n"
            f"STDOUT:\n{result_result.stdout}\n\n"
            f"STDERR:\n{result_result.stderr}"
        )

    if "status: finished" not in result_result.stdout.lower() and "status: completed" not in result_result.stdout.lower():
        for _ in range(max_runs - 1):
            last_run_result = run_app_command(
                f"{label}: run",
                "task",
                "run",
                task_id,
            )
            if not last_run_result.ok:
                raise RuntimeError(
                    f"{label} run failed for {task_id} with return code {last_run_result.returncode}\n"
                    f"STDOUT:\n{last_run_result.stdout}\n\n"
                    f"STDERR:\n{last_run_result.stderr}"
                )

            result_result = run_app_command(
                f"{label}: result",
                "task",
                "result",
                task_id,
            )
            if not result_result.ok:
                raise RuntimeError(
                    f"{label} result failed for {task_id} with return code {result_result.returncode}\n"
                    f"STDOUT:\n{result_result.stdout}\n\n"
                    f"STDERR:\n{result_result.stderr}"
                )

            lowered = result_result.stdout.lower()
            if "status: finished" in lowered or "status: completed" in lowered:
                break
            if "status: failed" in lowered:
                raise RuntimeError(f"{label} task failed: {task_id}\n{result_result.stdout}")
        else:
            raise RuntimeError(
                f"{label} task did not finish within {max_runs} runs: {task_id}\n"
                f"Last result:\n{result_result.stdout}"
            )

    artifact_ok, artifact_error = validate_text_artifact(output_path, label)
    if not artifact_ok:
        raise RuntimeError(artifact_error)

    return DocumentTaskResult(
        label=label,
        task_id=task_id,
        output_path=output_path,
        create_result=create_result,
        submit_result=submit_result,
        run_result=last_run_result,
        result_result=result_result,
    )


def run_summary(
    input_path: Path = DEFAULT_INPUT_PATH,
    output_path: Path = DEFAULT_SUMMARY_OUTPUT_PATH,
) -> DocumentTaskResult:
    return run_document_task(
        label="document summary",
        command_name="doc-summary",
        input_path=input_path,
        output_path=output_path,
    )


def run_action_items(
    input_path: Path = DEFAULT_INPUT_PATH,
    output_path: Path = DEFAULT_ACTION_ITEMS_OUTPUT_PATH,
) -> DocumentTaskResult:
    return run_document_task(
        label="document action-items",
        command_name="doc-action-items",
        input_path=input_path,
        output_path=output_path,
    )


def run_summary_and_action_items(
    input_path: Path = DEFAULT_INPUT_PATH,
    summary_output_path: Path = DEFAULT_SUMMARY_OUTPUT_PATH,
    action_items_output_path: Path = DEFAULT_ACTION_ITEMS_OUTPUT_PATH,
) -> DocumentFlowResult:
    try:
        ensure_required_paths()

        summary_task = run_summary(
            input_path=input_path,
            output_path=summary_output_path,
        )

        action_items_task = run_action_items(
            input_path=input_path,
            output_path=action_items_output_path,
        )

        return DocumentFlowResult(
            ok=True,
            input_path=input_path,
            summary_task=summary_task,
            action_items_task=action_items_task,
            error="",
        )

    except Exception as exc:
        return DocumentFlowResult(
            ok=False,
            input_path=input_path,
            summary_task=None,
            action_items_task=None,
            error=str(exc),
        )


def print_document_task_result(task: DocumentTaskResult) -> None:
    safe_print(f"[document-flow-orchestrator] {task.label}")
    safe_print(f"task_id: {task.task_id}")
    safe_print(f"artifact: {_to_repo_relative(task.output_path)}")
    safe_print("")


def print_document_flow_result(result: DocumentFlowResult) -> None:
    safe_print("[document-flow-orchestrator] input")
    safe_print(_to_repo_relative(result.input_path))
    safe_print("")

    if result.summary_task is not None:
        print_document_task_result(result.summary_task)

    if result.action_items_task is not None:
        print_document_task_result(result.action_items_task)

    if result.artifacts:
        safe_print("[document-flow-orchestrator] verified artifacts")
        for artifact in result.artifacts:
            safe_print(f"- {_to_repo_relative(artifact)}")
        safe_print("")

    if result.summary_task is not None and result.action_items_task is not None:
        safe_print("[document-flow-orchestrator] task lifecycle")
        safe_print(f"summary_task_id: {result.summary_task.task_id}")
        safe_print(f"action_items_task_id: {result.action_items_task.task_id}")
        safe_print("")

    if result.ok:
        safe_print("[document-flow-orchestrator] PASS")
        return

    safe_print("[document-flow-orchestrator] FAIL")
    if result.error:
        safe_print(result.error)


def main() -> int:
    input_path = write_default_input()
    result = run_summary_and_action_items(input_path=input_path)
    print_document_flow_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
