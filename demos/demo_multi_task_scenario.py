from __future__ import annotations

"""
Demo: multi-task queue scenario

Purpose:
- Create multiple independent tasks.
- Submit them into the official task lifecycle.
- Run the queue in small ticks.
- Prove one intentionally failing task does not block normal tasks.
- Collect task status, final answer, and trace availability into a demo summary.

Run from project root:

    python demos/demo_multi_task_scenario.py

Expected result:
- MULTI_DEMO_A finishes.
- MULTI_DEMO_B finishes.
- The missing-file verification task fails/replans/retries safely.
- A summary is written to workspace/shared/demo_multi_task_summary.txt.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP = PROJECT_ROOT / "app.py"

SUMMARY_PATH = PROJECT_ROOT / "workspace" / "shared" / "demo_multi_task_summary.txt"


@dataclass
class CliResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class DemoTask:
    label: str
    goal: str
    expected_final_answer: Optional[str] = None
    expected_to_finish: bool = True
    task_id: str = ""


def run_cli(args: List[str], *, check: bool = False) -> CliResult:
    command = [sys.executable, str(APP), *args]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    result = CliResult(
        command=command,
        returncode=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )

    if check and not result.ok:
        joined = " ".join(command)
        raise RuntimeError(
            f"Command failed: {joined}\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )

    return result


def extract_task_id(text: str) -> str:
    if not text:
        return ""

    # Prefer full task ids shown in CLI hint lines or JSON-like output.
    matches = re.findall(r"task_\d+", text)
    if matches:
        return matches[-1]

    # Fallback for short task_name/id style shown in planner output.
    matches = re.findall(r"task_[A-Za-z0-9]+", text)
    if matches:
        return matches[-1]

    return ""


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def task_dir(task_id: str) -> Path:
    return PROJECT_ROOT / "workspace" / "tasks" / task_id


def load_task_result(task_id: str) -> Dict[str, Any]:
    return read_json(task_dir(task_id) / "result.json", {})


def load_task_trace(task_id: str) -> List[Dict[str, Any]]:
    data = read_json(task_dir(task_id) / "trace.json", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        events = data.get("events")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
    return []


def show_task(task_id: str) -> str:
    result = run_cli(["task", "show", task_id])
    return (result.stdout or result.stderr or "").strip()


def create_task(task: DemoTask) -> str:
    result = run_cli(["task", "create", task.goal], check=True)
    task_id = extract_task_id(result.stdout)
    if not task_id:
        raise RuntimeError(
            f"Could not extract task_id for {task.label}.\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    task.task_id = task_id
    return task_id


def submit_task(task_id: str) -> None:
    run_cli(["task", "submit", task_id], check=True)


def run_queue_ticks(rounds: int = 4, count: int = 3) -> None:
    for _ in range(rounds):
        run_cli(["task", "run", str(count)], check=True)


def summarize_task(task: DemoTask) -> Dict[str, Any]:
    result_payload = load_task_result(task.task_id)
    trace_events = load_task_trace(task.task_id)
    show_text = show_task(task.task_id)

    status = ""
    final_answer = ""

    if isinstance(result_payload, dict):
        status = str(result_payload.get("status") or "")
        final_answer = str(
            result_payload.get("final_answer")
            or result_payload.get("result_summary")
            or result_payload.get("message")
            or ""
        )

    if not status:
        status_match = re.search(r"status:\s*([^\r\n]+)", show_text)
        if status_match:
            status = status_match.group(1).strip()

    if not final_answer:
        final_match = re.search(r"final_answer:\s*\r?\n\s*([^\r\n]+)", show_text)
        if final_match:
            final_answer = final_match.group(1).strip()

    trace_types = [
        str(event.get("type") or event.get("event") or "").strip()
        for event in trace_events
        if isinstance(event, dict)
    ]

    return {
        "label": task.label,
        "task_id": task.task_id,
        "goal": task.goal,
        "expected_to_finish": task.expected_to_finish,
        "expected_final_answer": task.expected_final_answer,
        "status": status,
        "final_answer": final_answer,
        "trace_event_count": len(trace_events),
        "trace_types": trace_types,
        "show_text": show_text,
    }


def evaluate(summary: Dict[str, Any]) -> bool:
    status = str(summary.get("status") or "").strip().lower()
    final_answer = str(summary.get("final_answer") or "").strip()
    expected_final_answer = summary.get("expected_final_answer")
    expected_to_finish = bool(summary.get("expected_to_finish"))

    if expected_to_finish:
        if status != "finished":
            return False
        if expected_final_answer and expected_final_answer not in final_answer:
            return False
        if int(summary.get("trace_event_count") or 0) <= 0:
            return False
        return True

    # For the intentionally failing task, acceptable outcomes are non-terminal
    # repair states or failed. The key point is that it does not block the
    # normal tasks.
    return status in {"failed", "retrying", "replanning", "blocked", "waiting"}


def write_summary(summaries: List[Dict[str, Any]]) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("ZERO multi-task demo summary")
    lines.append("=" * 30)
    lines.append("")
    lines.append("Purpose:")
    lines.append("- Create two normal tasks and one intentionally failing task.")
    lines.append("- Prove the failing task does not block normal queued work.")
    lines.append("- Confirm each task has observable task artifacts and trace data.")
    lines.append("")

    all_ok = True

    for item in summaries:
        ok = evaluate(item)
        all_ok = all_ok and ok

        lines.append(f"[{item['label']}] {'PASS' if ok else 'FAIL'}")
        lines.append(f"task_id: {item['task_id']}")
        lines.append(f"status: {item['status']}")
        lines.append(f"final_answer: {item['final_answer']}")
        lines.append(f"trace_event_count: {item['trace_event_count']}")

        trace_types = item.get("trace_types") or []
        if trace_types:
            lines.append(f"trace_types: {', '.join(trace_types)}")

        lines.append("")

    lines.append(f"overall: {'PASS' if all_ok else 'FAIL'}")
    lines.append("")

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("[multi-task-demo] creating tasks...")

    tasks = [
        DemoTask(
            label="A-normal",
            goal="write MULTI_DEMO_A to multi_demo_a.txt, then verify multi_demo_a.txt contains MULTI_DEMO_A",
            expected_final_answer="MULTI_DEMO_A",
            expected_to_finish=True,
        ),
        DemoTask(
            label="B-normal",
            goal="write MULTI_DEMO_B to multi_demo_b.txt, then verify multi_demo_b.txt contains MULTI_DEMO_B",
            expected_final_answer="MULTI_DEMO_B",
            expected_to_finish=True,
        ),
        DemoTask(
            label="C-intentional-failure",
            goal="verify missing_multi_demo_guard.txt contains SHOULD_NOT_EXIST",
            expected_final_answer=None,
            expected_to_finish=False,
        ),
    ]

    for task in tasks:
        create_task(task)
        print(f"[multi-task-demo] created {task.label}: {task.task_id}")

    print("[multi-task-demo] submitting tasks...")
    for task in tasks:
        submit_task(task.task_id)
        print(f"[multi-task-demo] submitted {task.label}: {task.task_id}")

    print("[multi-task-demo] running queue ticks...")
    run_queue_ticks(rounds=4, count=3)

    print("[multi-task-demo] collecting results...")
    summaries = [summarize_task(task) for task in tasks]
    write_summary(summaries)

    all_ok = all(evaluate(item) for item in summaries)

    for item in summaries:
        print(
            f"[multi-task-demo] {item['label']} "
            f"task_id={item['task_id']} "
            f"status={item['status']} "
            f"final_answer={item['final_answer']!r} "
            f"trace_events={item['trace_event_count']} "
            f"{'PASS' if evaluate(item) else 'FAIL'}"
        )

    print(f"[multi-task-demo] summary: {SUMMARY_PATH}")

    if all_ok:
        print("[multi-task-demo] PASS")
        return 0

    print("[multi-task-demo] FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
