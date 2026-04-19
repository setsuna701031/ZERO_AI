from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parent
APP_PATH = REPO_ROOT / "app.py"
MAINLINE_SMOKE_PATH = REPO_ROOT / "tests" / "run_mainline_smoke.py"
SHARED_DIR = REPO_ROOT / "workspace" / "shared"


def print_help() -> None:
    print("ZERO unified entry")
    print("")
    print("Usage:")
    print("  python main.py start")
    print("  python main.py runtime")
    print("  python main.py smoke")
    print("  python main.py doc-demo")
    print("  python main.py requirement-demo")
    print("  python main.py health")
    print("  python main.py help")
    print("")
    print("Commands:")
    print("  start             Launch interactive ZERO CLI")
    print("  runtime           Show runtime information")
    print("  smoke             Run stable mainline smoke validation")
    print("  doc-demo          Run end-to-end document demo flow")
    print("  requirement-demo  Run requirement-pack demo flow")
    print("  health            Show health information")
    print("  help              Show this help")


def run_process(args: List[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_required_paths() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"app.py not found: {APP_PATH}")
    SHARED_DIR.mkdir(parents=True, exist_ok=True)


def parse_task_id(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""

    try:
        payload = json.loads(stripped)
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

    match = re.search(r'"task_id"\s*:\s*"([^"]+)"', stripped)
    if match:
        return match.group(1).strip()

    return ""


def run_app_command(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return run_process([sys.executable, str(APP_PATH), *args], capture=capture)


def require_success(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with return code {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )


def write_doc_demo_input() -> Path:
    ensure_required_paths()
    input_path = SHARED_DIR / "input.txt"
    input_path.write_text(
        (
            "Alice will finish API draft by Friday. "
            "Bob will test the upload flow next week. "
            "A short stakeholder summary is needed. "
            "The team should review and finalize the project document."
        ),
        encoding="utf-8",
    )
    return input_path


def write_requirement_demo_input() -> Path:
    ensure_required_paths()
    input_path = SHARED_DIR / "requirement.txt"
    input_path.write_text(
        (
            "Build a local-first engineering agent demo scenario.\n\n"
            "Requirements:\n"
            "- Read a requirement document from workspace/shared/requirement.txt\n"
            "- Produce three outputs:\n"
            "  1. project_summary.txt\n"
            "  2. implementation_plan.txt\n"
            "  3. acceptance_checklist.txt\n\n"
            "Constraints:\n"
            "- Keep outputs in plain text\n"
            "- Do not use JSON\n"
            "- Make the plan engineering-oriented\n"
            "- Acceptance checklist must include:\n"
            "  Acceptance Criteria\n"
            "  Verification\n"
            "  Deliverable\n\n"
            "Expected deliverables:\n"
            "- A concise project summary\n"
            "- A practical implementation plan\n"
            "- A clear acceptance checklist\n"
        ),
        encoding="utf-8",
    )
    return input_path


def create_task(command_name: str, *args: str) -> str:
    result = run_app_command("task", command_name, *args, capture=True)
    require_success(result, f"create {command_name}")
    task_id = parse_task_id(result.stdout)
    if not task_id:
        raise RuntimeError(f"Could not parse task_id from {command_name}\n{result.stdout}")
    print(f"[task] created {command_name}: {task_id}")
    return task_id


def submit_task(task_id: str) -> None:
    result = run_app_command("task", "submit", task_id, capture=True)
    require_success(result, f"submit {task_id}")
    if '"ok": false' in (result.stdout or "").lower():
        raise RuntimeError(f"Submit failed for {task_id}\n{result.stdout}")
    print(f"[task] submitted: {task_id}")


def get_task_result_text(task_id: str) -> str:
    result = run_app_command("task", "result", task_id, capture=True)
    require_success(result, f"task result {task_id}")
    return result.stdout or ""


def get_task_show_text(task_id: str) -> str:
    result = run_app_command("task", "show", task_id, capture=True)
    require_success(result, f"task show {task_id}")
    return result.stdout or ""


def wait_until_finished(task_id: str, max_ticks: int = 10) -> None:
    last_output = ""
    for _ in range(max_ticks):
        tick = run_app_command("task", "run", "1", capture=True)
        require_success(tick, "task run 1")
        result_text = get_task_result_text(task_id)
        last_output = result_text
        lowered = result_text.lower()
        if "status: finished" in lowered or "status: completed" in lowered:
            print(f"[task] finished: {task_id}")
            return
        if "status: failed" in lowered:
            raise RuntimeError(f"Task failed: {task_id}\n{result_text}")
    raise RuntimeError(
        f"Task did not finish within {max_ticks} ticks: {task_id}\n"
        f"Last result output:\n{last_output}"
    )


def run_doc_demo() -> int:
    input_path = write_doc_demo_input()
    print(f"[doc-demo] input ready: {input_path}")

    summary_task_id = create_task("doc-summary", "input.txt", "summary_demo.txt")
    submit_task(summary_task_id)
    wait_until_finished(summary_task_id)

    action_task_id = create_task("doc-action-items", "input.txt", "action_items_demo.txt")
    submit_task(action_task_id)
    wait_until_finished(action_task_id)

    summary_result = get_task_result_text(summary_task_id)
    action_result = get_task_result_text(action_task_id)

    summary_output = SHARED_DIR / "summary_demo.txt"
    action_output = SHARED_DIR / "action_items_demo.txt"

    print("")
    print("[doc-demo] summary task result")
    print("----------------------------------------")
    print(summary_result.rstrip())
    print("")
    print("[doc-demo] action-items task result")
    print("----------------------------------------")
    print(action_result.rstrip())
    print("")
    print("[doc-demo] outputs")
    print(f"  summary: {summary_output}")
    print(f"  action items: {action_output}")
    print("[doc-demo] PASS")
    return 0


def run_requirement_demo() -> int:
    input_path = write_requirement_demo_input()
    print(f"[requirement-demo] input ready: {input_path}")

    task_id = create_task("requirement-pack", "requirement.txt")
    submit_task(task_id)
    wait_until_finished(task_id, max_ticks=5)

    result_text = get_task_result_text(task_id)
    show_text = get_task_show_text(task_id)

    project_summary_path = SHARED_DIR / "project_summary.txt"
    implementation_plan_path = SHARED_DIR / "implementation_plan.txt"
    acceptance_checklist_path = SHARED_DIR / "acceptance_checklist.txt"

    print("")
    print("[requirement-demo] task result")
    print("----------------------------------------")
    print(result_text.rstrip())
    print("")
    print("[requirement-demo] task show")
    print("----------------------------------------")
    print(show_text.rstrip())
    print("")
    print("[requirement-demo] outputs")
    print(f"  project summary: {project_summary_path}")
    print(f"  implementation plan: {implementation_plan_path}")
    print(f"  acceptance checklist: {acceptance_checklist_path}")
    print("[requirement-demo] PASS")
    return 0


def main(argv: List[str]) -> int:
    command = argv[1].strip().lower() if len(argv) >= 2 else "help"

    if command in {"help", "--help", "-h"}:
        print_help()
        return 0

    if command == "start":
        ensure_required_paths()
        result = run_app_command()
        return result.returncode

    if command == "runtime":
        ensure_required_paths()
        result = run_app_command("runtime", capture=False)
        return result.returncode

    if command == "health":
        ensure_required_paths()
        result = run_app_command("health", capture=False)
        return result.returncode

    if command == "smoke":
        if not MAINLINE_SMOKE_PATH.exists():
            raise FileNotFoundError(f"mainline smoke not found: {MAINLINE_SMOKE_PATH}")
        result = run_process([sys.executable, str(MAINLINE_SMOKE_PATH)], capture=False)
        return result.returncode

    if command == "doc-demo":
        return run_doc_demo()

    if command == "requirement-demo":
        return run_requirement_demo()

    print(f"Unknown command: {command}")
    print("")
    print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
