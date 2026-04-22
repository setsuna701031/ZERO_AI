from __future__ import annotations

import json
import locale
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "app.py"
WORKSPACE_DIR = REPO_ROOT / "workspace"
SHARED_DIR = WORKSPACE_DIR / "shared"


def run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(APP_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=False,
    )


def decode_output(data: bytes) -> str:
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


def stdout_text(result: subprocess.CompletedProcess) -> str:
    return decode_output(result.stdout or b"")


def stderr_text(result: subprocess.CompletedProcess) -> str:
    return decode_output(result.stderr or b"")


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


def ensure_shared_dir() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)


def write_input_file() -> Path:
    ensure_shared_dir()
    input_path = SHARED_DIR / "input.txt"
    input_path.write_text(
        (
            "Alice will finish API draft by Friday. "
            "Bob will test the upload flow next week. "
            "We need a short summary for the stakeholder meeting. "
            "The team should review and finalize the project document."
        ),
        encoding="utf-8",
    )
    return input_path


def parse_task_id(stdout: str) -> str:
    json_text = extract_first_json_object(stdout)
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

    match = re.search(r'"task_id"\s*:\s*"([^"]+)"', stdout)
    if match:
        return match.group(1).strip()

    raise RuntimeError(f"Could not parse task_id from output:\n{stdout}")


def assert_ok(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with return code {result.returncode}\n"
            f"STDOUT:\n{stdout_text(result)}\n\nSTDERR:\n{stderr_text(result)}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"{label} missing expected text: {needle}\n{text}")


def create_task(command_name: str, input_name: str, output_name: str) -> str:
    result = run_cmd("task", command_name, input_name, output_name)
    assert_ok(result, f"create {command_name}")
    task_id = parse_task_id(stdout_text(result))
    if not task_id:
        raise RuntimeError(f"{command_name}: empty task_id\n{stdout_text(result)}")
    return task_id


def submit_task(task_id: str) -> None:
    result = run_cmd("task", "submit", task_id)
    assert_ok(result, f"submit {task_id}")
    if '"ok": false' in stdout_text(result).lower():
        raise RuntimeError(f"submit failed for {task_id}\n{stdout_text(result)}")


def run_task_until_finished(task_id: str, max_ticks: int = 10) -> None:
    last_output = ""
    for _ in range(max_ticks):
        tick_result = run_cmd("task", "run", task_id)
        assert_ok(tick_result, f"task run for {task_id}")

        result_check = run_cmd("task", "result", task_id)
        assert_ok(result_check, f"task result for {task_id}")

        last_output = stdout_text(result_check)
        result_stdout_lower = last_output.lower()
        if "status: finished" in result_stdout_lower or "status: completed" in result_stdout_lower:
            return

    raise RuntimeError(
        f"Task did not finish within {max_ticks} runs: {task_id}\n"
        f"Last task result output:\n{last_output}"
    )


def read_task_result(task_id: str) -> str:
    result = run_cmd("task", "result", task_id)
    assert_ok(result, f"read task result {task_id}")
    return stdout_text(result)


def read_task_show(task_id: str) -> str:
    result = run_cmd("task", "show", task_id)
    assert_ok(result, f"read task show {task_id}")
    return stdout_text(result)


def assert_file_exists_and_not_empty(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise RuntimeError(f"{label} is empty: {path}")


def run_summary_flow() -> Dict[str, str]:
    task_id = create_task("doc-summary", "input.txt", "summary_smoke.txt")
    submit_task(task_id)
    run_task_until_finished(task_id)

    result_text = read_task_result(task_id)
    show_text = read_task_show(task_id)

    output_path = SHARED_DIR / "summary_smoke.txt"
    assert_file_exists_and_not_empty(output_path, "summary output")

    assert_contains(result_text, "status: finished", "summary task result")
    assert_contains(result_text, "final_answer:", "summary task result")
    assert_contains(show_text, "step: 3/3", "summary task show")
    assert_contains(show_text, "status: finished", "summary task show")
    assert_contains(show_text, "summary_smoke.txt", "summary task output path")

    output_text = output_path.read_text(encoding="utf-8", errors="replace")
    assert_true(
        "{{previous_result}}" not in output_text,
        "summary output should not contain literal placeholder",
    )

    return {
        "task_id": task_id,
        "output_path": str(output_path),
    }


def run_action_items_flow() -> Dict[str, str]:
    task_id = create_task("doc-action-items", "input.txt", "action_items_smoke.txt")
    submit_task(task_id)
    run_task_until_finished(task_id)

    result_text = read_task_result(task_id)
    show_text = read_task_show(task_id)

    output_path = SHARED_DIR / "action_items_smoke.txt"
    assert_file_exists_and_not_empty(output_path, "action items output")

    assert_contains(result_text, "status: finished", "action-items task result")
    assert_contains(result_text, "final_answer:", "action-items task result")
    assert_contains(result_text, "Alice", "action-items final answer")
    assert_contains(result_text, "Bob", "action-items final answer")
    assert_contains(result_text, "API", "action-items final answer")
    assert_contains(result_text, "upload", "action-items final answer")

    assert_contains(show_text, "step: 3/3", "action-items task show")
    assert_contains(show_text, "status: finished", "action-items task show")
    assert_contains(show_text, "action_items_smoke.txt", "action-items task output path")

    output_text = output_path.read_text(encoding="utf-8", errors="replace")
    assert_contains(output_text, "Alice", "action-items output file")
    assert_contains(output_text, "Bob", "action-items output file")
    assert_contains(output_text, "API", "action-items output file")
    assert_contains(output_text, "upload", "action-items output file")
    assert_true(
        "{{previous_result}}" not in output_text,
        "action-items output should not contain literal placeholder",
    )

    return {
        "task_id": task_id,
        "output_path": str(output_path),
    }


def main() -> int:
    print("[document-task-smoke] preparing input...")
    input_path = write_input_file()
    print(f"[document-task-smoke] input ready: {input_path}")

    print("[document-task-smoke] running summary flow...")
    summary_info = run_summary_flow()
    print(
        f"[document-task-smoke] summary PASS: "
        f"{summary_info['task_id']} -> {summary_info['output_path']}"
    )

    print("[document-task-smoke] running action-items flow...")
    action_info = run_action_items_flow()
    print(
        f"[document-task-smoke] action-items PASS: "
        f"{action_info['task_id']} -> {action_info['output_path']}"
    )

    print("[document-task-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())