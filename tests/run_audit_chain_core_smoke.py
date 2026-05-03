from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.audit.task_audit import load_audit_events, resolve_audit_log_path
from core.tasks.scheduler import Scheduler
from tests.isolation_helper import isolated_workspace


PREFIX = "[audit-chain-core-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def run_until_terminal(scheduler: Scheduler, task_id: str, max_ticks: int = 8) -> dict:
    last = {}
    for i in range(max_ticks):
        last = scheduler.tick(current_tick=i + 1)
        task = scheduler._get_task_from_repo(task_id)
        status = str((task or {}).get("status") or "").lower() if isinstance(task, dict) else ""
        if status in {"finished", "failed", "blocked"}:
            return task or last
    return scheduler._get_task_from_repo(task_id) or last


def events_for(workspace: Path, task_id: str) -> list[dict]:
    return load_audit_events(str(workspace), task_id=task_id)


def require_event(events: list[dict], event_type: str) -> dict:
    for event in events:
        if event.get("event_type") == event_type:
            return event
    return {}


def main() -> int:
    with isolated_workspace("audit_chain_core") as workspace:
        return run_smoke(workspace)


def run_smoke(workspace: Path) -> int:
    scheduler = Scheduler(workspace_dir=str(workspace), allow_commands=False)
    create = scheduler.create_task(
        goal="audit write shared :: step=write_file:shared/audit_chain_ok.txt|hello audit",
        source="test",
        max_replans=1,
    )
    if not create.get("ok"):
        return fail(f"create normal task failed: {create}")
    task_id = str(create.get("task_name") or create.get("task", {}).get("task_id") or "")
    submit = scheduler.submit_existing_task(task_id)
    if not submit.get("ok"):
        return fail(f"submit normal task failed: {submit}")
    final_task = run_until_terminal(scheduler, task_id)
    if final_task.get("status") != "finished":
        return fail(f"normal task did not finish: {final_task}")

    output_path = workspace / "shared" / "audit_chain_ok.txt"
    if output_path.read_text(encoding="utf-8") != "hello audit":
        return fail("normal write did not produce expected shared output")

    normal_events = events_for(workspace, task_id)
    if not normal_events:
        return fail(f"normal task audit events missing at {resolve_audit_log_path(str(workspace))}")
    if {event.get("source") for event in normal_events} != {"test"}:
        return fail(f"task source was not preserved in audit: {normal_events}")
    pass_step("task source is present in audit")

    policy_events = [event for event in normal_events if event.get("event_type") == "planned_or_policy"]
    if not any(event.get("policy_hint") for event in policy_events):
        return fail(f"policy_hint missing from audit: {normal_events}")
    if not any(event.get("policy_decision") in {"allow", "unknown"} for event in policy_events):
        return fail(f"policy_decision missing from audit: {normal_events}")
    if not any(event.get("policy_decision") == "allow" for event in policy_events):
        return fail(f"allow policy decision missing from guard audit: {normal_events}")
    pass_step("policy_hint and policy_decision are present in audit")

    terminal = require_event(normal_events, "execution_finished_or_failed")
    if terminal.get("execution_status") != "finished":
        return fail(f"execution_status missing after finish: {normal_events}")
    pass_step("execution_status is present after completion")

    repo_task = scheduler._get_task_from_repo(task_id)
    execution_log = repo_task.get("execution_log", []) if isinstance(repo_task, dict) else []
    if not execution_log or execution_log[-1].get("source") != "test":
        return fail(f"execution_log did not retain task source: {execution_log}")
    pass_step("execution_log retains task source")

    denied_path = workspace.parent / "audit_chain_denied_outside_workspace.txt"
    if denied_path.exists():
        return fail(f"denied test path unexpectedly exists before run: {denied_path}")

    denied = scheduler.create_task(
        goal=f"audit denied :: step=write_file:{denied_path}|should not write",
        source="test",
        max_replans=1,
    )
    if not denied.get("ok"):
        return fail(f"create denied task failed: {denied}")
    denied_task_id = str(denied.get("task_name") or denied.get("task", {}).get("task_id") or "")
    denied_submit = scheduler.submit_existing_task(denied_task_id)
    if not denied_submit.get("ok"):
        return fail(f"submit denied task failed: {denied_submit}")
    denied_final = run_until_terminal(scheduler, denied_task_id)
    if denied_path.exists():
        return fail(f"denied task wrote outside workspace: {denied_path}")
    if str(denied_final.get("status") or "").lower() not in {"failed", "blocked"}:
        return fail(f"denied task should fail or block: {denied_final}")

    denied_events = events_for(workspace, denied_task_id)
    if not any(event.get("policy_decision") == "deny" for event in denied_events):
        return fail(f"deny policy decision missing from audit: {denied_events}")
    if not require_event(denied_events, "execution_finished_or_failed"):
        return fail(f"denied task terminal audit missing: {denied_events}")
    pass_step("denied task is audited and does not write")

    legacy = scheduler._normalize_task_schema(
        {
            "task_id": "legacy_no_source_policy",
            "goal": "legacy task",
            "status": "queued",
        }
    )
    if legacy.get("source") != "unknown":
        return fail(f"legacy source fallback failed: {legacy}")
    if legacy.get("policy_decision") != "unknown":
        return fail(f"legacy policy fallback failed: {legacy}")
    json.dumps(legacy, ensure_ascii=False, default=str)
    pass_step("legacy task fallback source/policy is JSON serializable")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
