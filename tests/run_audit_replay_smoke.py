from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.audit.query import query_events_by_task_id
from core.audit.replay import compare_audit_event_sequence, replay_task_audit
from core.audit.task_audit import build_audit_event, write_audit_event
from tests.isolation_helper import isolated_workspace


PREFIX = "[audit-replay-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def seed_task(workspace: Path, task_id: str, trace_id: str, source: str = "test") -> None:
    task = {"task_id": task_id, "trace_file": trace_id, "source": source, "goal": "replay task"}
    rows = [
        build_audit_event(task=task, event_type="created", status="created"),
        build_audit_event(
            task=task,
            event_type="planned_or_policy",
            status="queued",
            policy_hint={"step_type": "write_file"},
            policy_decision="allow",
            policy_reason="guard allowed step",
            policy_source="ExecutionGuard.check_step",
        ),
        build_audit_event(
            task=task,
            event_type="execution_finished_or_failed",
            status="finished",
            execution_status="finished",
            policy_decision="allow",
            policy_reason="guard allowed step",
            policy_source="ExecutionGuard.check_step",
            result_summary="task finished",
        ),
    ]
    for row in rows:
        if not write_audit_event(str(workspace), row):
            raise RuntimeError("failed to seed audit event")


def main() -> int:
    with isolated_workspace("audit_replay") as workspace:
        seed_task(workspace, "task_a", "trace-a")
        seed_task(workspace, "task_b", "trace-b")

        summary = replay_task_audit(str(workspace), "task_a")
        if not summary.get("ok"):
            return fail(f"replay summary failed: {summary}")
        expected = {
            "has_created": True,
            "has_policy_event": True,
            "has_terminal_event": True,
            "final_status": "finished",
            "policy_decision": "allow",
            "execution_status": "finished",
            "source_consistent": True,
            "source": "test",
        }
        for key, value in expected.items():
            if summary.get(key) != value:
                return fail(f"summary {key} expected {value!r}, got {summary.get(key)!r}: {summary}")
        pass_step("replay summary")

        compare = compare_audit_event_sequence(
            query_events_by_task_id(str(workspace), "task_a"),
            query_events_by_task_id(str(workspace), "task_b"),
        )
        if compare.get("same_sequence") is not True:
            return fail(f"same sequence compare failed: {compare}")
        pass_step("compare same audit chain sequence")

        missing = replay_task_audit(str(workspace), "missing_task")
        if missing.get("ok") is not False or "not found" not in str(missing.get("error") or ""):
            return fail(f"missing task should return clear error: {missing}")
        pass_step("missing task returns clear error")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
