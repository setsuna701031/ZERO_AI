from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
WORKSPACE_SHARED = ROOT / "workspace" / "shared"


class SmokeFailure(RuntimeError):
    pass


def run_cmd(args: List[str], timeout: int = 180) -> Tuple[int, str]:
    process = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = ""
    if process.stdout:
        output += process.stdout
    if process.stderr:
        output += "\n[stderr]\n" + process.stderr
    return process.returncode, output.strip()


def app_cmd(*parts: str, timeout: int = 180) -> str:
    code, output = run_cmd([sys.executable, str(APP), *parts], timeout=timeout)
    if code != 0:
        raise SmokeFailure(
            "Command failed\n"
            f"command: python app.py {' '.join(parts)}\n"
            f"returncode: {code}\n"
            f"output:\n{output}"
        )
    return output


def extract_task_id(output: str) -> str:
    matches = re.findall(r"task_\d+", output or "")
    if not matches:
        raise SmokeFailure(f"Could not find task id in output:\n{output}")
    return matches[-1]


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SmokeFailure(
            f"Missing expected text for {label}: {needle!r}\n"
            f"Actual output:\n{text}"
        )


def assert_not_contains(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SmokeFailure(
            f"Unexpected text for {label}: {needle!r}\n"
            f"Actual output:\n{text}"
        )


def assert_file_text(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise SmokeFailure(f"{label} file was not created: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if text != expected:
        raise SmokeFailure(
            f"{label} file content mismatch.\n"
            f"path: {path}\n"
            f"expected: {expected!r}\n"
            f"actual: {text!r}"
        )


def assert_file_missing(path: Path, label: str) -> None:
    if path.exists():
        raise SmokeFailure(f"{label} should not exist, but it exists: {path}")


def create_submit_loop(goal: str, max_cycles: int = 8, timeout: int = 180) -> str:
    create_output = app_cmd("task", "create", goal, timeout=timeout)
    task_id = extract_task_id(create_output)

    submit_output = app_cmd("task", "submit", task_id, timeout=timeout)
    assert_contains(submit_output, '"ok": true', f"{task_id} submit")
    assert_contains(submit_output, '"status": "queued"', f"{task_id} submit queued")

    # Important:
    # Use target task loop instead of global "task run".
    # Global task run can spend time on old queued/running/replanning tasks in the repository.
    app_cmd("task", "loop", task_id, str(max_cycles), timeout=timeout)
    return task_id


def test_pure_write(stamp: str) -> None:
    target_rel = f"workspace/shared/l4_smoke_write_{stamp}.txt"
    target = ROOT / target_rel
    if target.exists():
        target.unlink()

    expected = f"L4_SMOKE_WRITE_OK_{stamp}"
    task_id = create_submit_loop(f"write {expected} to {target_rel}", max_cycles=8)

    show_output = app_cmd("task", "show", task_id)
    result_output = app_cmd("task", "result", task_id)

    assert_contains(show_output, "status: finished", "pure write show status")
    assert_contains(show_output, "step: 2/2", "pure write show progress")
    assert_contains(result_output, "status: finished", "pure write result status")
    assert_contains(result_output, expected, "pure write final_answer")
    assert_file_text(target, expected, "pure write artifact")

    print(f"[PASS] pure write lifecycle: {task_id}")


def test_missing_input_failure(stamp: str) -> None:
    missing_input_rel = f"workspace/shared/l4_missing_input_{stamp}.txt"
    missing_output_rel = f"workspace/shared/l4_missing_summary_{stamp}.txt"
    missing_input_path = ROOT / missing_input_rel
    missing_output_path = ROOT / missing_output_rel

    if missing_input_path.exists():
        missing_input_path.unlink()
    if missing_output_path.exists():
        missing_output_path.unlink()

    task_id = create_submit_loop(
        f"summarize {missing_input_rel} into {missing_output_rel}",
        max_cycles=8,
        timeout=180,
    )

    show_output = app_cmd("task", "show", task_id)
    result_output = app_cmd("task", "result", task_id)

    assert_contains(show_output, "status: failed", "missing input show status")
    assert_contains(show_output, "step: failed at 1/3", "missing input show progress")
    assert_contains(show_output.lower(), "file not found", "missing input show error")
    assert_contains(result_output, "status: failed", "missing input result status")
    assert_contains(result_output.lower(), "file not found", "missing input result error")
    assert_not_contains(show_output, "已讀取檔案", "missing input false success message")
    assert_file_missing(missing_output_path, "missing input output artifact")

    print(f"[PASS] missing input failure lifecycle: {task_id}")


def main() -> int:
    if not APP.is_file():
        print(f"[FAIL] app.py not found: {APP}")
        return 1

    WORKSPACE_SHARED.mkdir(parents=True, exist_ok=True)
    stamp = str(int(time.time()))
    print("[L4 smoke] start")
    print(f"[L4 smoke] root: {ROOT}")
    print(f"[L4 smoke] stamp: {stamp}")
    print("[L4 smoke] note: required smoke avoids LLM and uses target task loop.")

    try:
        test_pure_write(stamp)
        test_missing_input_failure(stamp)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    print("[PASS] L4 lifecycle smoke completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
