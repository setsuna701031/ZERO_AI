from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> int:
    print(f"[app-task-loop-cli-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[app-task-loop-cli-smoke] PASS: {message}")


def extract_json(stdout: str) -> Dict[str, Any]:
    text = str(stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < 0 or end < start:
        raise ValueError(f"no JSON object found in stdout: {text}")

    payload = text[start : end + 1]
    parsed = json.loads(payload)

    if not isinstance(parsed, dict):
        raise ValueError(f"parsed JSON is not dict: {parsed}")

    return parsed


def main() -> int:
    print("[app-task-loop-cli-smoke] START")

    command = [
        sys.executable,
        "app.py",
        "task",
        "loop",
        "task_not_exist",
        "2",
    ]

    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    print("[app-task-loop-cli-smoke] command")
    print(" ".join(command))

    if completed.stdout.strip():
        print("[app-task-loop-cli-smoke] STDOUT")
        print(completed.stdout.strip())

    if completed.stderr.strip():
        print("[app-task-loop-cli-smoke] STDERR")
        print(completed.stderr.strip())

    if completed.returncode != 0:
        return fail(f"command returned non-zero exit code: {completed.returncode}")

    try:
        payload = extract_json(completed.stdout)
    except Exception as e:
        return fail(f"failed to parse JSON output: {e}")

    if payload.get("ok") is not False:
        return fail(f"expected ok false, got: {payload.get('ok')}")

    if payload.get("mode") != "task_loop_until_terminal":
        return fail(f"expected mode task_loop_until_terminal, got: {payload.get('mode')}")

    if payload.get("task_id") != "task_not_exist":
        return fail(f"expected task_id task_not_exist, got: {payload.get('task_id')}")

    if payload.get("error") != "task not found":
        return fail(f"expected error task not found, got: {payload.get('error')}")

    pass_step("task loop CLI handles missing task safely")
    print("[app-task-loop-cli-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())