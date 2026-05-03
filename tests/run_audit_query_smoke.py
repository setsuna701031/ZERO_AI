from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.audit.query import (
    query_events_by_task_id,
    query_events_by_trace_id,
    query_recent_events,
    query_recent_problem_events,
)
from core.audit.task_audit import build_audit_event, write_audit_event
from tests.isolation_helper import isolated_workspace


PREFIX = "[audit-query-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def seed(workspace: Path) -> None:
    rows = [
        build_audit_event(
            task={"task_id": "task_a", "trace_file": "trace-a", "source": "test", "goal": "a"},
            event_type="created",
            status="created",
        ),
        build_audit_event(
            task={"task_id": "task_a", "trace_file": "trace-a", "source": "test", "goal": "a"},
            event_type="planned_or_policy",
            status="queued",
            policy_decision="allow",
            policy_reason="ok",
        ),
        build_audit_event(
            task={"task_id": "task_b", "trace_file": "trace-b", "source": "test", "goal": "b"},
            event_type="execution_finished_or_failed",
            status="failed",
            execution_status="failed",
            policy_decision="deny",
            error="guard blocked write",
        ),
    ]
    for row in rows:
        if not write_audit_event(str(workspace), row):
            raise RuntimeError("failed to seed audit event")


def main() -> int:
    with isolated_workspace("audit_query") as workspace:
        seed(workspace)

        by_task = query_events_by_task_id(str(workspace), "task_a")
        if len(by_task) != 2 or {event.get("task_id") for event in by_task} != {"task_a"}:
            return fail(f"query by task_id failed: {by_task}")
        pass_step("query by task_id")

        by_trace = query_events_by_trace_id(str(workspace), "trace-b")
        if len(by_trace) != 1 or by_trace[0].get("task_id") != "task_b":
            return fail(f"query by trace_id failed: {by_trace}")
        pass_step("query by trace_id")

        recent = query_recent_events(str(workspace), limit=2)
        if [event.get("task_id") for event in recent] != ["task_a", "task_b"]:
            return fail(f"recent events failed: {recent}")
        pass_step("recent events")

        problems = query_recent_problem_events(str(workspace), limit=5)
        if len(problems) != 1 or problems[0].get("execution_status") != "failed":
            return fail(f"recent problem events failed: {problems}")
        pass_step("recent error/failed/blocked events")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
