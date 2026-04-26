from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.task_runner import TaskRunner


SHARED_DIR = REPO_ROOT / "workspace" / "shared"

INPUT_PATH = SHARED_DIR / "task_runner_capability_input.txt"
SUMMARY_OUTPUT_PATH = SHARED_DIR / "task_runner_capability_summary.txt"
ACTION_ITEMS_OUTPUT_PATH = SHARED_DIR / "task_runner_capability_action_items.txt"


def fail(message: str) -> int:
    print(f"[task-runner-capability-gate-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[task-runner-capability-gate-smoke] PASS: {message}")


def write_input() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_PATH.write_text(
        (
            "Capability Gate Review Notes\n\n"
            "Alice will finish the integration draft by Friday.\n"
            "Bob will verify the task runner gate next week.\n"
            "Carol will prepare the release note before the internal demo.\n"
            "The team agreed that capability execution must remain gated and explicit.\n"
        ),
        encoding="utf-8",
    )


def require_file_nonempty(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"[task-runner-capability-gate-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[task-runner-capability-gate-smoke] not a file {label}: {path}")
        return False

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[task-runner-capability-gate-smoke] empty {label}: {path}")
        return False

    for marker in ("{{previous_result}}", "{{file_content}}"):
        if marker in text:
            print(f"[task-runner-capability-gate-smoke] unresolved marker in {label}: {marker}")
            return False

    pass_step(f"{label} exists and is non-empty")
    return True


def make_task() -> dict:
    task_id = "task_runner_capability_gate_smoke"

    return {
        "id": task_id,
        "task_id": task_id,
        "task_name": task_id,
        "title": "TaskRunner capability gate smoke",
        "goal": "Run document_flow capability through TaskRunner gate.",
        "status": "queued",
        "priority": 0,
        "task_dir": str(REPO_ROOT / "workspace" / "tasks" / task_id),
        "runtime_state_file": str(REPO_ROOT / "workspace" / "tasks" / task_id / "runtime_state.json"),
        "steps": [],
        "steps_total": 0,
        "current_step_index": 0,
        "results": [],
        "step_results": [],
        "execution_log": [],
        "execution_trace": [],
        "final_answer": "",
        "capability": "document_flow",
        "operation": "summary_and_action_items",
        "capability_hint": {
            "matched": True,
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "reason": "task_runner_capability_gate_smoke",
        },
        "capability_registry_hint": {
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "registry_operation": "run_summary_and_action_items",
            "capability_registered": True,
            "operation_registered": True,
        },
        "route": {
            "mode": "task",
            "task": True,
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "capability_hint": {
                "matched": True,
                "capability": "document_flow",
                "operation": "summary_and_action_items",
                "reason": "task_runner_capability_gate_smoke",
            },
            "capability_registry_hint": {
                "capability": "document_flow",
                "operation": "summary_and_action_items",
                "registry_operation": "run_summary_and_action_items",
                "capability_registered": True,
                "operation_registered": True,
            },
        },
        "capability_execution": {
            "enabled": True,
            "status": "pending",
            "reason": "explicit task runner capability gate smoke",
            "input_path": str(INPUT_PATH),
            "summary_output_path": str(SUMMARY_OUTPUT_PATH),
            "action_items_output_path": str(ACTION_ITEMS_OUTPUT_PATH),
        },
    }


def main() -> int:
    print("[task-runner-capability-gate-smoke] START")
    print(f"[task-runner-capability-gate-smoke] repo: {REPO_ROOT}")

    write_input()
    pass_step(f"input written: {INPUT_PATH}")

    for output_path in (SUMMARY_OUTPUT_PATH, ACTION_ITEMS_OUTPUT_PATH):
        if output_path.exists():
            output_path.unlink()

    task = make_task()
    runner = TaskRunner(debug=False)

    result = runner.run_task(task=task, current_tick=1)

    print("[task-runner-capability-gate-smoke] runner result")
    for key in ("ok", "action", "status", "final_answer", "error"):
        print(f"{key}: {result.get(key)}")

    if not result.get("ok"):
        return fail(f"TaskRunner returned non-ok: {result.get('error')}")

    if result.get("action") != "capability_executed":
        return fail(f"expected action capability_executed, got: {result.get('action')}")

    if str(result.get("status") or "").lower() != "finished":
        return fail(f"expected status finished, got: {result.get('status')}")

    runtime_state = result.get("runtime_state")
    if not isinstance(runtime_state, dict):
        return fail("runtime_state missing or invalid")

    capability_execution = runtime_state.get("capability_execution")
    if not isinstance(capability_execution, dict):
        return fail("runtime_state.capability_execution missing")

    if capability_execution.get("enabled") is not False:
        return fail("capability_execution.enabled should be False after execution")

    if capability_execution.get("status") != "finished":
        return fail(f"capability_execution.status should be finished, got: {capability_execution.get('status')}")

    checks = [
        require_file_nonempty(INPUT_PATH, "task runner capability input"),
        require_file_nonempty(SUMMARY_OUTPUT_PATH, "task runner capability summary output"),
        require_file_nonempty(ACTION_ITEMS_OUTPUT_PATH, "task runner capability action-items output"),
    ]

    if not all(checks):
        return fail("one or more artifact checks failed")

    print("[task-runner-capability-gate-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())