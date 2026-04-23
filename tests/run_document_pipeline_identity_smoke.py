from __future__ import annotations

import json
import locale
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
WORKSPACE_DIR = ROOT / "workspace"
SHARED_DIR = WORKSPACE_DIR / "shared"
TASKS_DIR = WORKSPACE_DIR / "tasks"

INPUT_TEXT = """Alice: Finish API draft by Friday. Bob: Test upload flow next week. Prepare summary for stakeholder meeting, finalise project document."""
REQUIREMENT_TEXT = """Build a local-first engineering agent demo scenario.

Requirements:
- Read a requirement document from workspace/shared/requirement_smoke.txt
- Produce three outputs:
  1. project_summary.txt
  2. implementation_plan.txt
  3. acceptance_checklist.txt

Constraints:
- Keep outputs in plain text
- Do not use JSON
- Make the plan engineering-oriented
- Acceptance checklist must include:
  Acceptance Criteria
  Verification
  Deliverable

Expected deliverables:
- A concise project summary
- A practical implementation plan
- A clear acceptance checklist
"""


PREFERRED_ENCODING = locale.getpreferredencoding(False) or "utf-8"


def run_cmd(args: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(APP_PATH)] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding=PREFERRED_ENCODING,
        errors="replace",
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def ensure_dirs() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def write_shared_inputs() -> Dict[str, Path]:
    ensure_dirs()
    input_path = SHARED_DIR / "input_smoke.txt"
    requirement_path = SHARED_DIR / "requirement_smoke.txt"
    input_path.write_text(INPUT_TEXT, encoding="utf-8")
    requirement_path.write_text(REQUIREMENT_TEXT, encoding="utf-8")
    return {"input": input_path, "requirement": requirement_path}


def parse_json_from_output(stdout: str) -> Dict:
    text = stdout or ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"JSON block not found in output:\n{text}")
    blob = text[start : end + 1]
    return json.loads(blob)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract_task_id(create_stdout: str) -> str:
    payload = parse_json_from_output(create_stdout)
    task_id = str(payload.get("task_id") or "").strip()
    expect(bool(task_id), f"task_id missing in create output:\n{create_stdout}")
    return task_id


def task_dir(task_id: str) -> Path:
    return TASKS_DIR / task_id


def load_json(path: Path) -> Dict:
    expect(path.is_file(), f"missing file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_identity_in_json(path: Path, expected: Dict[str, str]) -> None:
    payload = load_json(path)
    for key, value in expected.items():
        actual = str(payload.get(key) or "").strip()
        expect(actual == value, f"{path.name}: expected {key}={value!r}, got {actual!r}")


def verify_identity_in_cli(output: str, expected: Dict[str, str]) -> None:
    for key, value in expected.items():
        needle = f"{key}: {value}"
        expect(needle in output, f"missing CLI identity line: {needle}\nOutput:\n{output}")


def verify_finished(task_id: str, expected: Dict[str, str]) -> None:
    code, show_out, show_err = run_cmd(["task", "show", task_id])
    expect(code == 0, f"task show failed for {task_id}:\n{show_out}\n{show_err}")
    expect("status: finished" in show_out, f"task not finished in show:\n{show_out}")
    verify_identity_in_cli(show_out, expected)

    code, result_out, result_err = run_cmd(["task", "result", task_id])
    expect(code == 0, f"task result failed for {task_id}:\n{result_out}\n{result_err}")
    expect("status: finished" in result_out, f"task not finished in result:\n{result_out}")
    verify_identity_in_cli(result_out, expected)
    expect("final_answer:" in result_out, f"final_answer missing:\n{result_out}")


def verify_persisted_files(task_id: str, expected: Dict[str, str]) -> None:
    base = task_dir(task_id)
    verify_identity_in_json(base / "task_snapshot.json", expected)
    verify_identity_in_json(base / "runtime_state.json", expected)
    verify_identity_in_json(base / "result.json", expected)


def submit_and_run(task_id: str) -> None:
    code, submit_out, submit_err = run_cmd(["task", "submit", task_id])
    expect(code == 0, f"submit command failed:\n{submit_out}\n{submit_err}")
    submit_payload = parse_json_from_output(submit_out)
    expect(bool(submit_payload.get("ok")), f"submit not ok:\n{submit_out}")

    code, run_out, run_err = run_cmd(["task", "run", task_id])
    expect(code == 0, f"run command failed:\n{run_out}\n{run_err}")
    lower_blob = f"{run_out}\n{run_err}".lower()
    if "task not found" in lower_blob:
        raise AssertionError(f"task disappeared during run:\n{run_out}\n{run_err}")


def verify_file_exists(path: Path, label: str) -> None:
    expect(path.is_file(), f"missing {label}: {path}")
    content = path.read_text(encoding="utf-8").strip()
    expect(bool(content), f"empty {label}: {path}")


def run_summary_flow(input_path: Path) -> None:
    output_path = SHARED_DIR / "summary_identity_smoke.txt"
    if output_path.exists():
        output_path.unlink()

    code, out, err = run_cmd(["task", "doc-summary", str(input_path.relative_to(ROOT)), str(output_path.relative_to(ROOT))])
    expect(code == 0, f"doc-summary create failed:\n{out}\n{err}")
    task_id = extract_task_id(out)
    submit_and_run(task_id)

    expected = {
        "scenario": "doc_summary",
        "task_type": "document",
        "mode": "summary",
        "pipeline_name": "summary_pipeline",
        "execution_name": "summary_execution",
    }
    verify_finished(task_id, expected)
    verify_persisted_files(task_id, expected)
    verify_file_exists(output_path, "summary artifact")
    print(f"[PASS] summary pipeline identity smoke: {task_id}")


def run_action_items_flow(input_path: Path) -> None:
    output_path = SHARED_DIR / "action_items_identity_smoke.txt"
    if output_path.exists():
        output_path.unlink()

    code, out, err = run_cmd(["task", "doc-action-items", str(input_path.relative_to(ROOT)), str(output_path.relative_to(ROOT))])
    expect(code == 0, f"doc-action-items create failed:\n{out}\n{err}")
    task_id = extract_task_id(out)
    submit_and_run(task_id)

    expected = {
        "scenario": "doc_action_items",
        "task_type": "document",
        "mode": "action_items",
        "pipeline_name": "action_items_pipeline",
        "execution_name": "action_items_execution",
    }
    verify_finished(task_id, expected)
    verify_persisted_files(task_id, expected)
    verify_file_exists(output_path, "action_items artifact")
    print(f"[PASS] action_items pipeline identity smoke: {task_id}")


def run_requirement_flow(requirement_path: Path) -> None:
    for filename in ("project_summary.txt", "implementation_plan.txt", "acceptance_checklist.txt"):
        target = SHARED_DIR / filename
        if target.exists():
            target.unlink()

    code, out, err = run_cmd(["task", "doc-requirement", str(requirement_path.relative_to(ROOT))])
    expect(code == 0, f"doc-requirement create failed:\n{out}\n{err}")
    task_id = extract_task_id(out)
    submit_and_run(task_id)

    expected = {
        "scenario": "doc_requirement",
        "task_type": "document",
        "mode": "requirement",
        "pipeline_name": "requirement_pipeline",
        "execution_name": "requirement_execution",
    }
    verify_finished(task_id, expected)
    verify_persisted_files(task_id, expected)
    verify_file_exists(SHARED_DIR / "project_summary.txt", "project_summary artifact")
    verify_file_exists(SHARED_DIR / "implementation_plan.txt", "implementation_plan artifact")
    verify_file_exists(SHARED_DIR / "acceptance_checklist.txt", "acceptance_checklist artifact")
    print(f"[PASS] requirement pipeline identity smoke: {task_id}")


def main() -> int:
    if not APP_PATH.is_file():
        print(f"[FAIL] app.py not found: {APP_PATH}")
        return 1

    try:
        paths = write_shared_inputs()
        run_summary_flow(paths["input"])
        run_action_items_flow(paths["input"])
        run_requirement_flow(paths["requirement"])
        print("[document-pipeline-identity-smoke] ALL PASS")
        return 0
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
