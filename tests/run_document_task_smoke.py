from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "app.py"
WORKSPACE_DIR = REPO_ROOT / "workspace"
SHARED_DIR = WORKSPACE_DIR / "shared"


def run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(APP_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


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
    try:
        payload = json.loads(stdout)
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
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )


def create_task(command_name: str, input_name: str, output_name: str) -> str:
    result = run_cmd("task", command_name, input_name, output_name)
    assert_ok(result, f"create {command_name}")
    task_id = parse_task_id(result.stdout)
    if not task_id:
        raise RuntimeError(f"{command_name}: empty task_id\n{result.stdout}")
    return task_id


def submit_task(task_id: str) -> None:
    result = run_cmd("task", "submit", task_id)
    assert_ok(result, f"submit {task_id}")
    if '"ok": false' in result.stdout.lower():
        raise RuntimeError(f"submit failed for {task_id}\n{result.stdout}")


def run_task_until_finished(task_id: str, max_ticks: int = 10) -> None:
    for _ in range(max_ticks):
        tick_result = run_cmd("task", "run", "1")
        assert_ok(tick_result, f"task run for {task_id}")

        result_check = run_cmd("task", "result", task_id)
        assert_ok(result_check, f"task result for {task_id}")

        stdout_lower = result_check.stdout.lower()
        if "status: finished" in stdout_lower or "status: completed" in stdout_lower:
            return

    raise RuntimeError(
        f"Task did not finish within {max_ticks} ticks: {task_id}\n"
        f"Last task result output:\n{result_check.stdout}"
    )


def read_task_result(task_id: str) -> str:
    result = run_cmd("task", "result", task_id)
    assert_ok(result, f"read task result {task_id}")
    return result.stdout


def read_task_show(task_id: str) -> str:
    result = run_cmd("task", "show", task_id)
    assert_ok(result, f"read task show {task_id}")
    return result.stdout


def assert_file_exists_and_not_empty(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise RuntimeError(f"{label} is empty: {path}")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"{label} missing expected text: {needle}\n{text}")


def run_summary_flow() -> Dict[str, str]:
    task_id = create_task("doc-summary", "input.txt", "summary_smoke.txt")
    submit_task(task_id)
    run_task_until_finished(task_id)

    result_text = read_task_result(task_id)
    show_text = read_task_show(task_id)

    output_path = SHARED_DIR / "summary_smoke.txt"
    assert_file_exists_and_not_empty(output_path, "summary output")

    assert_contains(result_text, "status: finished", "summary task result")
    assert_contains(result_text, "shared_artifacts:", "summary task result")
    assert_contains(result_text, "summary_smoke.txt", "summary shared artifact")
    assert_contains(show_text, "step: 3/3", "summary task show")
    assert_contains(show_text, "shared_artifacts:", "summary task show")
    assert_contains(show_text, "summary_smoke.txt", "summary task show artifact")

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
    assert_contains(result_text, "ACTION ITEMS", "action-items final answer")
    assert_contains(result_text, "shared_artifacts:", "action-items task result")
    assert_contains(result_text, "action_items_smoke.txt", "action-items shared artifact")
    assert_contains(show_text, "step: 3/3", "action-items task show")
    assert_contains(show_text, "shared_artifacts:", "action-items task show")
    assert_contains(show_text, "action_items_smoke.txt", "action-items task show artifact")

    output_text = output_path.read_text(encoding="utf-8", errors="replace")
    assert_contains(output_text, "ACTION ITEMS", "action-items output file")
    assert_contains(output_text, "Owner:", "action-items output file")
    assert_contains(output_text, "Task:", "action-items output file")

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
    print(f"[document-task-smoke] summary PASS: {summary_info['task_id']} -> {summary_info['output_path']}")

    print("[document-task-smoke] running action-items flow...")
    action_info = run_action_items_flow()
    print(f"[document-task-smoke] action-items PASS: {action_info['task_id']} -> {action_info['output_path']}")

    print("[document-task-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())