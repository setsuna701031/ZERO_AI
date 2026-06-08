from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.workflow_runtime_session import WorkflowRuntimeSessionManager, build_workflow_runtime_session
from core.runtime.runtime_replay_engine import build_replayable_workflow_runtime_session, build_governance_storage_lifecycle_replay_validation, build_governance_kernel_consolidation_replay_validation
from core.runtime.repair_step_injector import build_repair_injection
from core.runtime.repair_planner import plan_repair


def test_workflow_session_records_full_phase_chain_from_execution_log() -> None:
    task = {"task_id": "wf-demo", "steps": [{"id": "s1", "type": "command"}]}
    state = {
        "task_id": "wf-demo",
        "status": "finished",
        "steps": [
            {"id": "exec", "type": "command"},
            {"id": "verify", "type": "verify_python_syntax"},
            {"id": "repair", "type": "governed_repair_mutation"},
            {"id": "rollback", "type": "rollback"},
        ],
        "execution_log": [
            {"step_index": 0, "step": {"type": "command"}, "result": {"ok": True, "step_index": 0, "step_type": "command"}, "tick": 1},
            {"step_index": 1, "step": {"type": "verify_python_syntax"}, "result": {"ok": True, "step_index": 1}, "tick": 2},
            {"step_index": 2, "step": {"type": "governed_repair_mutation"}, "result": {"ok": True, "step_index": 2}, "tick": 3},
            {"step_index": 3, "step": {"type": "rollback"}, "result": {"ok": True, "step_index": 3}, "tick": 4},
        ],
    }

    session = build_workflow_runtime_session(task=task, state=state)

    assert session["schema"] == "zero.workflow_runtime_session.v1"
    assert session["status"] == "finished"
    assert session["replayable"] is True
    assert session["phases"]["planner"]["seen"] is True
    assert session["phases"]["execution"]["seen"] is True
    assert session["phases"]["verify"]["seen"] is True
    assert session["phases"]["repair"]["seen"] is True
    assert session["phases"]["rollback_retry"]["seen"] is True
    assert session["phases"]["replayable_session"]["seen"] is True
    assert len(session["events"]) == 4


def test_workflow_session_append_step_result_is_deterministic_and_public_safe() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-append", "steps": [{"type": "command"}]}
    state = {"task_id": "wf-append", "status": "running", "steps": [{"type": "command"}], "current_step_index": 0}
    step = {"type": "command", "command": "python -V"}
    step_result = {"ok": True, "step_index": 0, "message": "done"}

    session_a = manager.append_step_result(task=task, state=state, step=step, step_result=step_result, current_tick=1)
    state["workflow_runtime_session"] = session_a
    session_b = manager.append_step_result(task=task, state=state, step=step, step_result=step_result, current_tick=1)

    assert session_a["session_id"] == session_b["session_id"]
    assert session_a["result_hash"] == session_b["result_hash"]
    assert len(session_b["events"]) == 1

    public = manager.finalize_public_result(task=task, state=state, result={"ok": True, "status": "running", "runtime_state": state})
    assert public["aer_workflow_runtime"]["schema"] == "zero.workflow_runtime_session.v1"
    assert public["aer_workflow_runtime"]["replayable"] is True


def test_runtime_replay_engine_exposes_workflow_session_bridge() -> None:
    task = {"task_id": "wf-replay", "steps": [{"type": "verify"}]}
    state = {
        "task_id": "wf-replay",
        "status": "finished",
        "steps": [{"type": "verify"}],
        "execution_log": [
            {"step_index": 0, "step": {"type": "verify"}, "result": {"ok": True, "step_index": 0}, "tick": 1}
        ],
    }

    result = build_replayable_workflow_runtime_session(task=task, runtime_state=state)

    assert result["ok"] is True
    assert result["replayable"] is True
    assert result["workflow_runtime_session"]["phases"]["verify"]["seen"] is True


def test_workflow_session_identity_and_lineage_survive_verify_repair_retry_replay() -> None:
    failed_step = {"id": "verify", "type": "verify_python_syntax", "path": "bad.py"}
    failed_result = {"ok": False, "step_index": 1, "error": {"message": "SyntaxError"}}
    task = {"task_id": "wf-lineage", "steps": [{"type": "command"}]}
    state = {
        "task_id": "wf-lineage",
        "status": "finished",
        "steps": [
            {"id": "exec", "type": "command"},
            failed_step,
            {"id": "repair", "type": "governed_repair_mutation"},
            {"id": "retry", "type": "retry"},
        ],
        "repair_context": {
            "original_failed_step": failed_step,
            "original_failed_result": failed_result,
            "strategy": {"retry_count": 1},
        },
        "execution_log": [
            {"step_index": 0, "step": {"type": "command"}, "result": {"ok": True, "step_index": 0}, "tick": 1},
            {"step_index": 1, "step": failed_step, "result": failed_result, "tick": 2},
            {"step_index": 2, "step": {"type": "governed_repair_mutation"}, "result": {"ok": True, "step_index": 2}, "tick": 3},
            {"step_index": 3, "step": {"type": "retry"}, "result": {"ok": True, "step_index": 3, "action": "retry"}, "tick": 4},
        ],
    }

    session = build_workflow_runtime_session(task=task, state=state)
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={"workflow_runtime_session": session, **state})

    assert session["session_id"]
    assert session["workflow_id"]
    assert session["continuity_summary"]["ok"] is True
    assert {event["session_id"] for event in session["events"]} == {session["session_id"]}
    assert {event["workflow_id"] for event in session["events"]} == {session["workflow_id"]}
    assert session["phases"]["verify"]["seen"] is True
    assert session["phases"]["repair"]["seen"] is True
    assert session["phases"]["rollback_retry"]["seen"] is True
    assert session["lineage"]["retry_chain"]
    assert replay["source_session_id"] == session["session_id"]
    assert replay["replay_continuation"]["source_session_id"] == session["session_id"]


def test_repair_steps_and_events_preserve_parent_failed_references() -> None:
    failed_step = {"id": "verify", "type": "verify_python_syntax", "path": "bad.py"}
    failed_result = {"ok": False, "step_index": 1, "error": {"message": "SyntaxError"}}
    repair_plan = {
        "ok": True,
        "classification": "python_syntax_error",
        "summary": "repair candidate",
        "actions": [{"type": "write_file", "path": "bad_repaired.py", "content": "x = 1\n"}],
    }

    injection = build_repair_injection(
        repair_plan=repair_plan,
        task={"task_id": "wf-repair-ancestry"},
        failed_step=failed_step,
        failed_result=failed_result,
    )
    repair_step = injection["steps"][0]
    ancestry = repair_step["repair_ancestry"]

    assert ancestry["parent_failed_step_ref"]
    assert ancestry["parent_failed_result_ref"]
    assert ancestry["parent_failed_step"] == failed_step

    session = build_workflow_runtime_session(
        task={"task_id": "wf-repair-ancestry", "steps": [failed_step, repair_step]},
        state={
            "task_id": "wf-repair-ancestry",
            "steps": [failed_step, repair_step],
            "execution_log": [
                {"step_index": 0, "step": failed_step, "result": failed_result, "tick": 1},
                {"step_index": 1, "step": repair_step, "result": {"ok": True, "step_index": 1}, "tick": 2},
            ],
        },
    )
    repair_event = [event for event in session["events"] if event["phase"] == "repair"][0]

    assert repair_event["lineage"]["repair_ancestry"]["parent_failed_step_ref"]
    assert repair_event["lineage"]["repair_ancestry"]["parent_failed_result_ref"]


def test_continuity_summary_reports_broken_source_or_parent_linkage() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-broken", "steps": [{"type": "command"}]}
    state = {
        "task_id": "wf-broken",
        "source_session_id": "source-session",
        "replay_continuation": {"source_session_id": "source-session"},
        "steps": [{"type": "command"}],
        "execution_log": [
            {"step_index": 0, "step": {"type": "command"}, "result": {"ok": True, "step_index": 0}, "tick": 1}
        ],
    }
    session = build_workflow_runtime_session(task=task, state=state)

    assert session["continuity_summary"]["ok"] is True

    broken_source = dict(session)
    broken_source["lineage"] = dict(session["lineage"])
    broken_source["lineage"]["replay_continuation"] = {"source_session_id": "wrong-source"}
    assert manager.continuity_summary(broken_source)["ok"] is False

    broken_parent = dict(session)
    broken_parent["events"] = [dict(event) for event in session["events"]]
    broken_parent["events"][0]["lineage"] = dict(broken_parent["events"][0]["lineage"])
    broken_parent["events"][0]["lineage"]["parent_event_id"] = "missing-parent-event"
    assert manager.continuity_summary(broken_parent)["ok"] is False


def test_workflow_runtime_use_path_intent_to_replay_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    intent = {
        "task_id": "wf-use-path",
        "goal": "repair a Python syntax failure",
    }
    task = {
        "task_id": "wf-use-path",
        "goal": intent["goal"],
        "steps": [],
    }
    state = {
        "task_id": "wf-use-path",
        "status": "running",
        "steps": [],
    }

    session = manager.start_from_intent(intent=intent, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    workflow_id = session["workflow_id"]
    session_id = session["session_id"]

    plan = {
        "ok": True,
        "steps": [
            {"id": "execute", "type": "command", "command": "python -m py_compile bad.py"},
            {"id": "verify", "type": "verify_python_syntax", "path": "bad.py"},
        ],
    }
    task["steps"] = plan["steps"]
    state["steps"] = plan["steps"]
    session = manager.attach_plan_record(task=task, state=state, plan=plan, current_tick=2)
    state["workflow_runtime_session"] = session

    assert session["workflow_id"] == workflow_id
    assert session["session_id"] == session_id
    assert session["events"][-1]["event_type"] == "plan"

    execute_step = plan["steps"][0]
    execute_result = {
        "ok": True,
        "step_index": 0,
        "message": "execution completed",
    }
    session = manager.attach_execution_record(
        task=task,
        state=state,
        step=execute_step,
        result=execute_result,
        current_tick=3,
    )
    state["workflow_runtime_session"] = session

    assert session["workflow_id"] == workflow_id
    assert session["session_id"] == session_id
    assert session["phases"]["execution"]["seen"] is True

    verify_step = plan["steps"][1]
    verify_result = {
        "ok": False,
        "step_index": 1,
        "command": "python -m py_compile bad.py",
        "stderr": "SyntaxError: invalid syntax",
        "source_text": "def add(a, b):\n    return a +\n",
        "error": {"message": "SyntaxError: invalid syntax"},
    }
    session = manager.attach_verify_record(
        task=task,
        state=state,
        verify_step=verify_step,
        verify_result=verify_result,
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    state["repair_context"] = {
        "original_failed_step": verify_step,
        "original_failed_result": session["events"][-1]["payload"]["result"],
    }

    classification = session["events"][-1]["payload"]["result"]["verification_classification"]
    assert classification["classification"] == "python_syntax_error"
    assert classification["repair_required"] is True

    repair_plan = plan_repair(
        step_result=verify_result,
        source_text=verify_result["source_text"],
        source_path="bad.py",
    )
    assert repair_plan["ok"] is True
    assert repair_plan["classification"] == "python_syntax_error"

    injection = build_repair_injection(
        repair_plan=repair_plan,
        task=task,
        failed_step=verify_step,
        failed_result=verify_result,
    )
    assert injection["ok"] is True
    repair_step = injection["steps"][0]
    assert repair_step["repair_ancestry"]["parent_failed_step_ref"]
    assert repair_step["repair_ancestry"]["parent_failed_result_ref"]

    state["steps"] = [*state["steps"], *injection["steps"]]
    task["steps"] = state["steps"]
    session = manager.attach_repair_record(
        task=task,
        state=state,
        repair_step=repair_step,
        repair_result={
            "ok": True,
            "step_index": 2,
            "repair_ancestry": repair_step["repair_ancestry"],
        },
        current_tick=5,
    )
    state["workflow_runtime_session"] = session

    repair_event = session["events"][-1]
    assert repair_event["workflow_id"] == workflow_id
    assert repair_event["session_id"] == session_id
    assert repair_event["lineage"]["repair_ancestry"]["parent_failed_step_ref"]

    session = manager.attach_retry_continuation_record(
        task=task,
        state=state,
        retry_record={
            "step": {"id": "retry", "type": "retry"},
            "result": {"ok": True, "step_index": 3, "action": "retry", "retry_count": 1},
        },
        current_tick=6,
    )
    state["workflow_runtime_session"] = session

    retry_chain = session["lineage"]["retry_chain"][-1]
    assert session["workflow_id"] == workflow_id
    assert session["session_id"] == session_id
    assert retry_chain["repair_ancestry"]["parent_failed_step_ref"]

    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={**state, "workflow_runtime_session": session},
    )
    assert replay["source_session_id"] == session_id
    assert replay["replay_continuation"]["source_session_id"] == session_id
    assert replay["workflow_id"] == workflow_id
    assert replay["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["ok"] is True

    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    broken["events"][1]["workflow_id"] = "wrong-workflow"
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "event_workflow_id_mismatch" in broken_summary["breaks"]


def test_workflow_runtime_checkpoint_restore_resume_replay_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    intent = {"task_id": "wf-checkpoint", "goal": "continue after checkpoint"}
    task = {"task_id": "wf-checkpoint", "goal": intent["goal"], "steps": []}
    state = {"task_id": "wf-checkpoint", "status": "running", "steps": []}

    session = manager.start_from_intent(intent=intent, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    workflow_id = session["workflow_id"]
    session_id = session["session_id"]

    plan = {
        "ok": True,
        "steps": [
            {"id": "execute", "type": "command", "command": "python -m py_compile bad.py"},
            {"id": "verify", "type": "verify_python_syntax", "path": "bad.py"},
        ],
    }
    task["steps"] = plan["steps"]
    state["steps"] = plan["steps"]
    session = manager.attach_plan_record(task=task, state=state, plan=plan, current_tick=2)
    state["workflow_runtime_session"] = session

    session = manager.attach_execution_record(
        task=task,
        state=state,
        step=plan["steps"][0],
        result={"ok": True, "step_index": 0, "message": "executed"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session

    verify_result = {
        "ok": False,
        "step_index": 1,
        "command": "python -m py_compile bad.py",
        "stderr": "SyntaxError: invalid syntax",
        "source_text": "def add(a, b):\n    return a +\n",
        "error": {"message": "SyntaxError: invalid syntax"},
    }
    session = manager.attach_verify_record(
        task=task,
        state=state,
        verify_step=plan["steps"][1],
        verify_result=verify_result,
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    state["repair_context"] = {
        "original_failed_step": plan["steps"][1],
        "original_failed_result": session["events"][-1]["payload"]["result"],
    }

    repair_plan = plan_repair(
        step_result=verify_result,
        source_text=verify_result["source_text"],
        source_path="bad.py",
    )
    injection = build_repair_injection(
        repair_plan=repair_plan,
        task=task,
        failed_step=plan["steps"][1],
        failed_result=verify_result,
    )
    repair_step = injection["steps"][0]
    state["steps"] = [*state["steps"], *injection["steps"]]
    task["steps"] = state["steps"]
    session = manager.attach_repair_record(
        task=task,
        state=state,
        repair_step=repair_step,
        repair_result={"ok": True, "step_index": 2, "repair_ancestry": repair_step["repair_ancestry"]},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session

    session = manager.create_checkpoint(
        task=task,
        state=state,
        label="after_repair_before_retry",
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    checkpoint_event = session["events"][-1]
    checkpoint_record = checkpoint_event["payload"]["record"]

    assert checkpoint_event["event_type"] == "checkpoint"
    assert checkpoint_record["checkpoint_id"]
    assert checkpoint_record["workflow_id"] == workflow_id
    assert checkpoint_record["session_id"] == session_id

    restored_state = {**state, "status": "running", "workflow_runtime_session": session}
    restored_session = manager.restore_from_checkpoint(
        task=task,
        state=restored_state,
        checkpoint=checkpoint_record,
        current_tick=7,
    )
    restored_state["workflow_runtime_session"] = restored_session

    restore_event = restored_session["events"][-1]
    assert restore_event["event_type"] == "restore"
    assert restore_event["lineage"]["restore"]["source_checkpoint_id"] == checkpoint_record["checkpoint_id"]
    assert restored_session["workflow_id"] == workflow_id
    assert restored_session["session_id"] == session_id

    resumed_session = manager.attach_resume_continue_record(
        task=task,
        state=restored_state,
        resume_record={
            "step": {"id": "retry-after-restore", "type": "retry"},
            "result": {"ok": True, "step_index": 3, "action": "resume_continue", "retry_count": 1},
        },
        current_tick=8,
    )
    restored_state["workflow_runtime_session"] = resumed_session

    retry_chain = resumed_session["lineage"]["retry_chain"][-1]
    resume_chain = resumed_session["lineage"]["resume_continuations"][-1]
    assert retry_chain["repair_ancestry"]["parent_failed_step_ref"]
    assert resume_chain["checkpoint_id"] == checkpoint_record["checkpoint_id"]
    assert resumed_session["continuity_summary"]["ok"] is True

    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={**restored_state, "workflow_runtime_session": resumed_session},
    )
    assert replay["source_session_id"] == session_id
    assert replay["workflow_id"] == workflow_id
    assert replay["continuity_summary"]["ok"] is True

    json.dumps(resumed_session, sort_keys=True, default=str)

    broken = dict(resumed_session)
    broken["events"] = [dict(event) for event in resumed_session["events"]]
    broken["events"][-2]["lineage"] = dict(broken["events"][-2]["lineage"])
    broken["events"][-2]["lineage"]["restore"] = dict(broken["events"][-2]["lineage"]["restore"])
    broken["events"][-2]["lineage"]["restore"]["source_checkpoint_id"] = "missing-checkpoint"
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "missing_restore_source_checkpoint" in broken_summary["breaks"]


def test_workflow_runtime_execution_memory_recovery_resume_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    intent = {"task_id": "wf-memory", "goal": "recover from execution memory"}
    task = {"task_id": "wf-memory", "goal": intent["goal"], "steps": []}
    state = {"task_id": "wf-memory", "status": "running", "steps": []}

    session = manager.start_from_intent(intent=intent, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    workflow_id = session["workflow_id"]
    session_id = session["session_id"]

    plan = {
        "ok": True,
        "steps": [
            {"id": "execute", "type": "command", "command": "python -m py_compile bad.py"},
            {"id": "verify", "type": "verify_python_syntax", "path": "bad.py"},
        ],
    }
    task["steps"] = plan["steps"]
    state["steps"] = plan["steps"]
    session = manager.attach_plan_record(task=task, state=state, plan=plan, current_tick=2)
    state["workflow_runtime_session"] = session
    session = manager.attach_execution_record(
        task=task,
        state=state,
        step=plan["steps"][0],
        result={"ok": True, "step_index": 0, "message": "executed"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session

    verify_result = {
        "ok": False,
        "step_index": 1,
        "command": "python -m py_compile bad.py",
        "stderr": "SyntaxError: invalid syntax",
        "source_text": "def add(a, b):\n    return a +\n",
        "error": {"message": "SyntaxError: invalid syntax"},
    }
    session = manager.attach_verify_record(
        task=task,
        state=state,
        verify_step=plan["steps"][1],
        verify_result=verify_result,
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    state["repair_context"] = {
        "original_failed_step": plan["steps"][1],
        "original_failed_result": session["events"][-1]["payload"]["result"],
    }

    repair_plan = plan_repair(
        step_result=verify_result,
        source_text=verify_result["source_text"],
        source_path="bad.py",
    )
    injection = build_repair_injection(
        repair_plan=repair_plan,
        task=task,
        failed_step=plan["steps"][1],
        failed_result=verify_result,
    )
    repair_step = injection["steps"][0]
    state["steps"] = [*state["steps"], *injection["steps"]]
    task["steps"] = state["steps"]
    session = manager.attach_repair_record(
        task=task,
        state=state,
        repair_step=repair_step,
        repair_result={"ok": True, "step_index": 2, "repair_ancestry": repair_step["repair_ancestry"]},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session

    session = manager.create_checkpoint(task=task, state=state, label="memory_resume", current_tick=6)
    state["workflow_runtime_session"] = session
    checkpoint_record = session["events"][-1]["payload"]["record"]

    session = manager.restore_from_checkpoint(task=task, state=state, checkpoint=checkpoint_record, current_tick=7)
    state["workflow_runtime_session"] = session
    restore_event_id = session["events"][-1]["event_id"]

    session = manager.persist_execution_cursor(
        task=task,
        state=state,
        cursor={
            "step_index": 3,
            "step_id": "retry-after-restore",
            "phase": "rollback_retry",
            "checkpoint_id": checkpoint_record["checkpoint_id"],
            "restore_event_id": restore_event_id,
        },
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    cursor = session["lineage"]["execution_cursors"][-1]
    assert cursor["workflow_id"] == workflow_id
    assert cursor["session_id"] == session_id
    assert cursor["checkpoint_id"] == checkpoint_record["checkpoint_id"]

    session = manager.append_execution_memory(
        task=task,
        state=state,
        memory={
            "entry_type": "resume_context",
            "payload": {
                "last_failed_step": plan["steps"][1]["id"],
                "next_step_index": 3,
            },
        },
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    memory = session["lineage"]["execution_memory"][-1]
    assert memory["cursor_id"] == cursor["cursor_id"]

    session = manager.create_recovery_resume_point(
        task=task,
        state=state,
        resume_point={
            "reason": "continue after restored repair checkpoint",
            "step_index": 3,
        },
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    resume_point = session["lineage"]["recovery_resume_points"][-1]
    assert resume_point["cursor_id"] == cursor["cursor_id"]
    assert resume_point["memory_id"] == memory["memory_id"]

    session = manager.resume_from_recovery_point(
        task=task,
        state=state,
        recovery_resume_point=resume_point,
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    recovery_resume = session["lineage"]["recovery_resumes"][-1]
    assert recovery_resume["recovery_resume_id"] == resume_point["recovery_resume_id"]
    assert recovery_resume["cursor_id"] == cursor["cursor_id"]

    session = manager.attach_resume_continue_record(
        task=task,
        state=state,
        resume_record={
            "step": {"id": "retry-after-recovery-resume", "type": "retry"},
            "result": {"ok": True, "step_index": 3, "action": "resume_continue", "retry_count": 2},
        },
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    assert session["continuity_summary"]["ok"] is True

    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={**state, "workflow_runtime_session": session},
    )
    replay_session = replay["workflow_runtime_session"]
    assert replay["source_session_id"] == session_id
    assert replay_session["lineage"]["replay_continuation"]["recovery_resume_id"] == recovery_resume["recovery_resume_id"]
    assert replay_session["continuity_summary"]["ok"] is True

    json.dumps(replay_session, sort_keys=True, default=str)

    broken_cursor = dict(session)
    broken_cursor["events"] = [dict(event) for event in session["events"]]
    for event in broken_cursor["events"]:
        if event["event_type"] == "recovery_resume_point":
            event["lineage"] = dict(event["lineage"])
            event["lineage"]["recovery_resume_point"] = dict(event["lineage"]["recovery_resume_point"])
            event["lineage"]["recovery_resume_point"]["cursor_id"] = "missing-cursor"
            break
    broken_cursor_summary = manager.continuity_summary(broken_cursor)
    assert broken_cursor_summary["ok"] is False
    assert "recovery_resume_point_cursor_id_mismatch" in broken_cursor_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["recovery_resume_id"] = "wrong-recovery-resume"
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_recovery_resume_id_mismatch" in broken_replay_summary["breaks"]


def test_workflow_runtime_execution_graph_recovery_graph_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    intent = {"task_id": "wf-graph", "goal": "continue across branch graph lineage"}
    task = {"task_id": "wf-graph", "goal": intent["goal"], "steps": []}
    state = {"task_id": "wf-graph", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent=intent, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    workflow_id = session["workflow_id"]
    session_id = session["session_id"]

    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-root", "branch_id": "main", "label": "root", "step_index": 0},
        current_tick=2,
    )
    state["workflow_runtime_session"] = session

    session = manager.create_branch_fork(
        task=task,
        state=state,
        branch={"branch_id": "branch-a", "parent_branch_id": "main", "fork_node_id": "node-root", "name": "repair path"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    session = manager.create_branch_fork(
        task=task,
        state=state,
        branch={"branch_id": "branch-b", "parent_branch_id": "main", "fork_node_id": "node-root", "name": "alternate path"},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "branch-a"
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-a1", "branch_id": "branch-a", "parent_node_id": "node-root", "label": "branch a execute", "step_index": 1},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    session = manager.connect_graph_edge(
        task=task,
        state=state,
        edge={"edge_id": "edge-root-a1", "from_node_id": "node-root", "to_node_id": "node-a1", "branch_id": "branch-a"},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session

    failed_step = {"id": "verify-a", "type": "verify_python_syntax", "path": "bad.py"}
    failed_result = {"ok": False, "step_index": 2, "error": {"message": "SyntaxError"}}
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-a-verify", "branch_id": "branch-a", "parent_node_id": "node-a1", "label": "verify failure", "phase": "verify", "step_index": 2},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_verify_record(
        task=task,
        state=state,
        verify_step=failed_step,
        verify_result=failed_result,
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    state["repair_context"] = {
        "original_failed_step": failed_step,
        "original_failed_result": failed_result,
    }
    repair_plan = {
        "ok": True,
        "classification": "python_syntax_error",
        "summary": "repair branch syntax failure",
        "actions": [{"type": "write_file", "path": "bad.py", "content": "def f():\n    return 1\n"}],
    }
    injection = build_repair_injection(
        repair_plan=repair_plan,
        task=task,
        failed_step=failed_step,
        failed_result=failed_result,
    )
    repair_step = injection["steps"][0]
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-a-repair", "branch_id": "branch-a", "parent_node_id": "node-a-verify", "label": "repair", "phase": "repair", "step_index": 3},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_repair_record(
        task=task,
        state=state,
        repair_step=repair_step,
        repair_result={"ok": True, "step_index": 3, "repair_ancestry": repair_step["repair_ancestry"]},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_recovery_dependency(
        task=task,
        state=state,
        dependency={
            "recovery_dependency_id": "dep-verify-repair",
            "source_node_id": "node-a-verify",
            "target_node_id": "node-a-repair",
            "branch_id": "branch-a",
            "dependency_type": "verify_failure_repair",
        },
        current_tick=11,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "branch-b"
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-b1", "branch_id": "branch-b", "parent_node_id": "node-root", "label": "branch b execute", "step_index": 1},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    session = manager.connect_graph_edge(
        task=task,
        state=state,
        edge={"edge_id": "edge-root-b1", "from_node_id": "node-root", "to_node_id": "node-b1", "branch_id": "branch-b"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "main"
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "node-join", "branch_id": "main", "parent_node_id": "node-root", "label": "join", "step_index": 4},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.connect_graph_edge(
        task=task,
        state=state,
        edge={"edge_id": "edge-a-repair-join", "from_node_id": "node-a-repair", "to_node_id": "node-join", "branch_id": "main", "edge_type": "merge"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session
    session = manager.connect_graph_edge(
        task=task,
        state=state,
        edge={"edge_id": "edge-b1-join", "from_node_id": "node-b1", "to_node_id": "node-join", "branch_id": "main", "edge_type": "merge"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session
    session = manager.create_join_merge(
        task=task,
        state=state,
        join={
            "join_id": "join-ab-main",
            "source_branch_ids": ["branch-a", "branch-b"],
            "target_branch_id": "main",
            "join_node_id": "node-join",
        },
        current_tick=17,
    )
    state["workflow_runtime_session"] = session

    assert session["workflow_id"] == workflow_id
    assert session["session_id"] == session_id
    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["ok"] is True
    assert session["lineage"]["execution_graph"]["nodes"]
    assert session["lineage"]["execution_graph"]["edges"]
    assert session["lineage"]["execution_graph"]["branches"]
    assert session["lineage"]["execution_graph"]["joins"]
    assert session["lineage"]["recovery_dependency_graph"]["dependencies"]

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "branch-a",
        "continued_branch_id": "main",
    }
    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={**state, "workflow_runtime_session": session},
    )
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["lineage"]["replay_continuation"]["source_branch_id"] == "branch-a"
    assert replay_session["lineage"]["replay_continuation"]["continued_branch_id"] == "main"
    assert replay_session["continuity_summary"]["ok"] is True

    json.dumps(replay_session, sort_keys=True, default=str)

    broken_edge = dict(session)
    broken_edge["lineage"] = dict(session["lineage"])
    broken_edge["lineage"]["execution_graph"] = dict(session["lineage"]["execution_graph"])
    broken_edge["lineage"]["execution_graph"]["edges"] = [dict(item) for item in session["lineage"]["execution_graph"]["edges"]]
    broken_edge["lineage"]["execution_graph"]["edges"][0]["from_node_id"] = "missing-node"
    broken_edge_summary = manager.continuity_summary(broken_edge)
    assert broken_edge_summary["ok"] is False
    assert "orphan_graph_edge" in broken_edge_summary["breaks"]

    broken_branch = dict(session)
    broken_branch["lineage"] = dict(session["lineage"])
    broken_branch["lineage"]["execution_graph"] = dict(session["lineage"]["execution_graph"])
    broken_branch["lineage"]["execution_graph"]["branches"] = [dict(item) for item in session["lineage"]["execution_graph"]["branches"]]
    broken_branch["lineage"]["execution_graph"]["branches"][0]["parent_branch_id"] = "missing-branch"
    broken_branch_summary = manager.continuity_summary(broken_branch)
    assert broken_branch_summary["ok"] is False
    assert "broken_branch_parent" in broken_branch_summary["breaks"]

    broken_join = dict(session)
    broken_join["lineage"] = dict(session["lineage"])
    broken_join["lineage"]["execution_graph"] = dict(session["lineage"]["execution_graph"])
    broken_join["lineage"]["execution_graph"]["joins"] = [dict(item) for item in session["lineage"]["execution_graph"]["joins"]]
    broken_join["lineage"]["execution_graph"]["joins"][0]["join_node_id"] = "missing-join-node"
    broken_join_summary = manager.continuity_summary(broken_join)
    assert broken_join_summary["ok"] is False
    assert "invalid_join_lineage" in broken_join_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["continued_branch_id"] = "unrelated-branch"
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_branch_lineage_mismatch" in broken_replay_summary["breaks"]


def test_workflow_runtime_mutation_transaction_rollback_graph_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    intent = {"task_id": "wf-mutation-graph", "goal": "rollback mutation branch safely"}
    task = {"task_id": "wf-mutation-graph", "goal": intent["goal"], "steps": []}
    state = {"task_id": "wf-mutation-graph", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent=intent, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, branch in ((2, {"node_id": "root", "branch_id": "main", "label": "root"}),):
        session = manager.create_execution_graph_node(task=task, state=state, node=branch, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.create_branch_fork(
        task=task,
        state=state,
        branch={"branch_id": "branch-a", "parent_branch_id": "main", "fork_node_id": "root"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    session = manager.create_branch_fork(
        task=task,
        state=state,
        branch={"branch_id": "branch-b", "parent_branch_id": "main", "fork_node_id": "root"},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "branch-a"
    for tick, node in (
        (5, {"node_id": "mut-a", "branch_id": "branch-a", "parent_node_id": "root", "label": "mutation"}),
        (6, {"node_id": "verify-a", "branch_id": "branch-a", "parent_node_id": "mut-a", "label": "verify", "phase": "verify"}),
        (7, {"node_id": "rollback-a", "branch_id": "branch-a", "parent_node_id": "verify-a", "label": "rollback", "phase": "rollback_retry"}),
        (8, {"node_id": "retry-a", "branch_id": "branch-a", "parent_node_id": "rollback-a", "label": "retry", "phase": "rollback_retry"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    mutation = {
        "mutation_transaction_id": "mutation-a",
        "node_id": "mut-a",
        "branch_id": "branch-a",
        "mutation_type": "write_file",
        "payload": {"path": "bad.py", "content": "def f():\n    return +\n"},
    }
    session = manager.attach_mutation_transaction(task=task, state=state, mutation=mutation, current_tick=9)
    state["workflow_runtime_session"] = session

    verify = {
        "mutation_verify_id": "verify-mutation-a",
        "mutation_transaction_id": "mutation-a",
        "verify_node_id": "verify-a",
        "branch_id": "branch-a",
        "ok": False,
        "failure_classification": "python_syntax_error",
    }
    session = manager.attach_mutation_verify_record(task=task, state=state, verify=verify, current_tick=10)
    state["workflow_runtime_session"] = session

    rollback = {
        "rollback_id": "rollback-mutation-a",
        "rollback_node_id": "rollback-a",
        "mutation_transaction_id": "mutation-a",
        "mutation_verify_id": "verify-mutation-a",
        "branch_id": "branch-a",
        "retry_node_id": "retry-a",
        "reason": "verify failed",
    }
    session = manager.attach_rollback_graph_node(task=task, state=state, rollback=rollback, current_tick=11)
    state["workflow_runtime_session"] = session
    session = manager.attach_recovery_dependency(
        task=task,
        state=state,
        dependency={
            "recovery_dependency_id": "dep-rollback-retry",
            "source_node_id": "rollback-a",
            "target_node_id": "retry-a",
            "branch_id": "branch-a",
            "dependency_type": "rollback_retry",
        },
        current_tick=12,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "branch-b"
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "branch-b-node", "branch_id": "branch-b", "parent_node_id": "root", "label": "alternate mutation"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_mutation_transaction(
        task=task,
        state=state,
        mutation={
            "mutation_transaction_id": "mutation-b",
            "node_id": "branch-b-node",
            "branch_id": "branch-b",
            "mutation_type": "write_file",
            "payload": {"path": "bad.py", "content": "def f():\n    return 2\n"},
        },
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_mutation_verify_record(
        task=task,
        state=state,
        verify={
            "mutation_verify_id": "verify-mutation-b",
            "mutation_transaction_id": "mutation-b",
            "verify_node_id": "branch-b-node",
            "branch_id": "branch-b",
            "ok": True,
        },
        current_tick=15,
    )
    state["workflow_runtime_session"] = session

    state["current_branch_id"] = "main"
    session = manager.create_execution_graph_node(
        task=task,
        state=state,
        node={"node_id": "join-mutation", "branch_id": "main", "parent_node_id": "root", "label": "join"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session
    session = manager.create_join_merge(
        task=task,
        state=state,
        join={"join_id": "join-mutation-main", "source_branch_ids": ["branch-a", "branch-b"], "target_branch_id": "main", "join_node_id": "join-mutation"},
        current_tick=17,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_branch_conflict_record(
        task=task,
        state=state,
        conflict={
            "conflict_id": "conflict-ab",
            "source_branch_ids": ["branch-a", "branch-b"],
            "target_branch_id": "main",
            "conflict_node_id": "join-mutation",
            "mutation_transaction_ids": ["mutation-a", "mutation-b"],
        },
        current_tick=18,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_graph_reconciliation_record(
        task=task,
        state=state,
        reconciliation={
            "reconciliation_id": "reconcile-ab",
            "conflict_id": "conflict-ab",
            "rollback_id": "rollback-mutation-a",
            "retry_node_id": "retry-a",
            "source_branch_ids": ["branch-a", "branch-b"],
            "target_branch_id": "main",
        },
        current_tick=19,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["mutation_transaction_count"] == 2
    assert session["continuity_summary"]["graph_continuity"]["rollback_count"] == 1
    assert session["lineage"]["mutation_transaction_graph"]["mutations"]
    assert session["lineage"]["rollback_graph"]["rollbacks"]

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "branch-a",
        "continued_branch_id": "main",
        "mutation_transaction_ids": ["mutation-a", "mutation-b"],
        "rollback_ids": ["rollback-mutation-a"],
    }
    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={**state, "workflow_runtime_session": session},
    )
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["lineage"]["replay_continuation"]["mutation_transaction_ids"] == ["mutation-a", "mutation-b"]
    assert replay_session["lineage"]["replay_continuation"]["rollback_ids"] == ["rollback-mutation-a"]
    assert replay_session["continuity_summary"]["ok"] is True
    json.dumps(replay_session, sort_keys=True, default=str)

    broken_rollback = dict(session)
    broken_rollback["lineage"] = dict(session["lineage"])
    broken_rollback["lineage"]["rollback_graph"] = dict(session["lineage"]["rollback_graph"])
    broken_rollback["lineage"]["rollback_graph"]["rollbacks"] = [dict(item) for item in session["lineage"]["rollback_graph"]["rollbacks"]]
    broken_rollback["lineage"]["rollback_graph"]["rollbacks"][0]["mutation_transaction_id"] = "missing-mutation"
    broken_rollback_summary = manager.continuity_summary(broken_rollback)
    assert broken_rollback_summary["ok"] is False
    assert "rollback_without_mutation_parent" in broken_rollback_summary["breaks"]

    broken_verify = dict(session)
    broken_verify["events"] = [dict(event) for event in session["events"]]
    for event in broken_verify["events"]:
        event["lineage"] = dict(event["lineage"])
        event["lineage"].pop("mutation_verify", None)
    broken_verify["lineage"] = dict(session["lineage"])
    broken_verify["lineage"]["mutation_transaction_graph"] = dict(session["lineage"]["mutation_transaction_graph"])
    broken_verify["lineage"]["mutation_transaction_graph"]["verifies"] = []
    broken_verify_summary = manager.continuity_summary(broken_verify)
    assert broken_verify_summary["ok"] is False
    assert "mutation_verify_record_missing" in broken_verify_summary["breaks"]

    broken_conflict = dict(session)
    broken_conflict["lineage"] = dict(session["lineage"])
    broken_conflict["lineage"]["mutation_transaction_graph"] = dict(session["lineage"]["mutation_transaction_graph"])
    broken_conflict["lineage"]["mutation_transaction_graph"]["conflicts"] = [dict(item) for item in session["lineage"]["mutation_transaction_graph"]["conflicts"]]
    broken_conflict["lineage"]["mutation_transaction_graph"]["conflicts"][0]["source_branch_ids"] = ["branch-a", "unrelated-branch"]
    broken_conflict_summary = manager.continuity_summary(broken_conflict)
    assert broken_conflict_summary["ok"] is False
    assert "branch_conflict_unrelated_branches" in broken_conflict_summary["breaks"]

    broken_reconciliation = dict(session)
    broken_reconciliation["lineage"] = dict(session["lineage"])
    broken_reconciliation["lineage"]["mutation_transaction_graph"] = dict(session["lineage"]["mutation_transaction_graph"])
    broken_reconciliation["lineage"]["mutation_transaction_graph"]["reconciliations"] = [dict(item) for item in session["lineage"]["mutation_transaction_graph"]["reconciliations"]]
    broken_reconciliation["lineage"]["mutation_transaction_graph"]["reconciliations"][0]["retry_node_id"] = "missing-retry"
    broken_reconciliation_summary = manager.continuity_summary(broken_reconciliation)
    assert broken_reconciliation_summary["ok"] is False
    assert "reconciliation_missing_rollback_retry_link" in broken_reconciliation_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["mutation_transaction_ids"] = ["stale-mutation"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_stale_mutation_lineage" in broken_replay_summary["breaks"]


def test_workflow_runtime_governance_state_authority_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-governance", "steps": []}
    state = {"task_id": "wf-governance", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-governance", "goal": "govern mutation"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    session = manager.create_execution_graph_node(task=task, state=state, node={"node_id": "root-gov", "branch_id": "main"}, current_tick=2)
    state["workflow_runtime_session"] = session
    session = manager.create_branch_fork(task=task, state=state, branch={"branch_id": "branch-gov", "parent_branch_id": "main", "fork_node_id": "root-gov"}, current_tick=3)
    state["workflow_runtime_session"] = session
    state["current_branch_id"] = "branch-gov"
    for tick, node in (
        (4, {"node_id": "exec-gov", "branch_id": "branch-gov", "parent_node_id": "root-gov"}),
        (5, {"node_id": "mut-gov", "branch_id": "branch-gov", "parent_node_id": "exec-gov"}),
        (6, {"node_id": "verify-gov", "branch_id": "branch-gov", "parent_node_id": "mut-gov", "phase": "verify"}),
        (7, {"node_id": "rollback-gov", "branch_id": "branch-gov", "parent_node_id": "verify-gov", "phase": "rollback_retry"}),
        (8, {"node_id": "resume-gov", "branch_id": "branch-gov", "parent_node_id": "rollback-gov", "phase": "rollback_retry"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_mutation_transaction(
        task=task,
        state=state,
        mutation={"mutation_transaction_id": "mutation-gov", "node_id": "mut-gov", "branch_id": "branch-gov", "payload": {"path": "guarded.py"}},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_mutation_verify_record(
        task=task,
        state=state,
        verify={"mutation_verify_id": "verify-gov-mutation", "mutation_transaction_id": "mutation-gov", "verify_node_id": "verify-gov", "branch_id": "branch-gov", "ok": False},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_rollback_graph_node(
        task=task,
        state=state,
        rollback={"rollback_id": "rollback-gov-mutation", "rollback_node_id": "rollback-gov", "mutation_transaction_id": "mutation-gov", "mutation_verify_id": "verify-gov-mutation", "branch_id": "branch-gov", "retry_node_id": "resume-gov"},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_recovery_dependency(
        task=task,
        state=state,
        dependency={"recovery_dependency_id": "dep-gov-rollback", "source_node_id": "rollback-gov", "target_node_id": "resume-gov", "branch_id": "branch-gov"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "policy-gov", "target_node_id": "mut-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov", "policy_id": "mutation-policy", "allowed": False, "decision": "review_required"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"authority_id": "authority-gov", "target_node_id": "mut-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov", "execution_owner": "TaskRunner", "authority_source": "StepExecutor"},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_review_required_record(
        task=task,
        state=state,
        review={"review_id": "review-gov", "policy_decision_id": "policy-gov", "target_node_id": "mut-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_approval_record(
        task=task,
        state=state,
        approval={"approval_id": "approval-gov", "review_id": "review-gov", "policy_decision_id": "policy-gov", "target_node_id": "mut-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_governance_resume_record(
        task=task,
        state=state,
        resume={"governance_resume_id": "resume-gov-record", "approval_id": "approval-gov", "review_id": "review-gov", "resumed_node_id": "resume-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov"},
        current_tick=17,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitution_enforcement_record(
        task=task,
        state=state,
        enforcement={"enforcement_id": "enforcement-gov", "target_node_id": "mut-gov", "mutation_transaction_id": "mutation-gov", "branch_id": "branch-gov", "rule_id": "execution_constitution"},
        current_tick=18,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["governance_record_count"] == 6
    assert session["lineage"]["governance_state_graph"]["policy_decisions"]
    assert session["lineage"]["governance_state_graph"]["authority"]

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "branch-gov",
        "continued_branch_id": "branch-gov",
        "mutation_transaction_ids": ["mutation-gov"],
        "rollback_ids": ["rollback-gov-mutation"],
        "governance_record_ids": ["policy-gov", "authority-gov", "review-gov", "approval-gov", "resume-gov-record", "enforcement-gov"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["governance_record_ids"][-1] == "enforcement-gov"
    json.dumps(replay_session, sort_keys=True, default=str)

    broken_policy = dict(session)
    broken_policy["lineage"] = dict(session["lineage"])
    broken_policy["lineage"]["governance_state_graph"] = dict(session["lineage"]["governance_state_graph"])
    broken_policy["lineage"]["governance_state_graph"]["policy_decisions"] = [dict(item) for item in session["lineage"]["governance_state_graph"]["policy_decisions"]]
    broken_policy["lineage"]["governance_state_graph"]["policy_decisions"][0]["target_node_id"] = "missing-node"
    broken_policy_summary = manager.continuity_summary(broken_policy)
    assert broken_policy_summary["ok"] is False
    assert "policy_decision_target_missing" in broken_policy_summary["breaks"]

    broken_authority = dict(session)
    broken_authority["lineage"] = dict(session["lineage"])
    broken_authority["lineage"]["governance_state_graph"] = dict(session["lineage"]["governance_state_graph"])
    broken_authority["lineage"]["governance_state_graph"]["authority"] = [dict(item) for item in session["lineage"]["governance_state_graph"]["authority"]]
    broken_authority["lineage"]["governance_state_graph"]["authority"][0]["session_id"] = "wrong-session"
    broken_authority_summary = manager.continuity_summary(broken_authority)
    assert broken_authority_summary["ok"] is False
    assert "authority_lineage_mismatch" in broken_authority_summary["breaks"]

    broken_approval = dict(session)
    broken_approval["lineage"] = dict(session["lineage"])
    broken_approval["lineage"]["governance_state_graph"] = dict(session["lineage"]["governance_state_graph"])
    broken_approval["lineage"]["governance_state_graph"]["approvals"] = [dict(item) for item in session["lineage"]["governance_state_graph"]["approvals"]]
    broken_approval["lineage"]["governance_state_graph"]["approvals"][0]["review_id"] = "missing-review"
    broken_approval_summary = manager.continuity_summary(broken_approval)
    assert broken_approval_summary["ok"] is False
    assert "approval_without_review_parent" in broken_approval_summary["breaks"]

    broken_resume = dict(session)
    broken_resume["lineage"] = dict(session["lineage"])
    broken_resume["lineage"]["governance_state_graph"] = dict(session["lineage"]["governance_state_graph"])
    broken_resume["lineage"]["governance_state_graph"]["resumes"] = [dict(item) for item in session["lineage"]["governance_state_graph"]["resumes"]]
    broken_resume["lineage"]["governance_state_graph"]["resumes"][0]["approval_id"] = "missing-approval"
    broken_resume_summary = manager.continuity_summary(broken_resume)
    assert broken_resume_summary["ok"] is False
    assert "resume_without_approval_parent" in broken_resume_summary["breaks"]

    broken_enforcement = dict(session)
    broken_enforcement["lineage"] = dict(session["lineage"])
    broken_enforcement["lineage"]["governance_state_graph"] = dict(session["lineage"]["governance_state_graph"])
    broken_enforcement["lineage"]["governance_state_graph"]["constitution_enforcements"] = [dict(item) for item in session["lineage"]["governance_state_graph"]["constitution_enforcements"]]
    broken_enforcement["lineage"]["governance_state_graph"]["constitution_enforcements"][0]["target_node_id"] = "missing-node"
    broken_enforcement["lineage"]["governance_state_graph"]["constitution_enforcements"][0]["mutation_transaction_id"] = "missing-mutation"
    broken_enforcement_summary = manager.continuity_summary(broken_enforcement)
    assert broken_enforcement_summary["ok"] is False
    assert "constitution_enforcement_unrelated_target" in broken_enforcement_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["governance_record_ids"] = ["stale-governance"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_stale_governance_lineage" in broken_replay_summary["breaks"]


def test_workflow_runtime_multi_actor_federation_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-federation", "steps": []}
    state = {"task_id": "wf-federation", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-federation", "goal": "coordinate workers"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, node in (
        (2, {"node_id": "fed-root", "branch_id": "main"}),
        (3, {"node_id": "fed-exec-a", "branch_id": "main", "parent_node_id": "fed-root"}),
        (4, {"node_id": "fed-exec-b", "branch_id": "main", "parent_node_id": "fed-exec-a"}),
        (5, {"node_id": "fed-recovery", "branch_id": "main", "parent_node_id": "fed-exec-b"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "fed-policy", "target_node_id": "fed-exec-a", "branch_id": "main", "allowed": True},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"authority_id": "fed-authority-local", "target_node_id": "fed-exec-a", "branch_id": "main", "execution_owner": "TaskRunner"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_actor_worker_record(task=task, state=state, worker={"worker_id": "worker-a", "actor_id": "actor-a"}, current_tick=8)
    state["workflow_runtime_session"] = session
    session = manager.attach_actor_worker_record(task=task, state=state, worker={"worker_id": "worker-b", "actor_id": "actor-b"}, current_tick=9)
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_federation_record(
        task=task,
        state=state,
        federation={"federation_id": "federation-ab", "worker_ids": ["worker-a", "worker-b"], "coordinator_worker_id": "worker-a"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_distributed_execution_record(
        task=task,
        state=state,
        execution={"distributed_execution_id": "dx-a", "worker_id": "worker-a", "federation_id": "federation-ab", "target_node_id": "fed-exec-a"},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_distributed_execution_record(
        task=task,
        state=state,
        execution={"distributed_execution_id": "dx-b", "worker_id": "worker-b", "parent_worker_ids": ["worker-a"], "federation_id": "federation-ab", "target_node_id": "fed-exec-b"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_distributed_recovery_record(
        task=task,
        state=state,
        recovery={"distributed_recovery_id": "dr-b", "source_execution_id": "dx-b", "recovery_worker_id": "worker-a", "recovery_node_id": "fed-recovery"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_federated_authority_record(
        task=task,
        state=state,
        authority={"federated_authority_id": "fa-a", "worker_id": "worker-a", "authority_id": "fed-authority-local", "federation_id": "federation-ab"},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_distributed_governance_record(
        task=task,
        state=state,
        governance={"distributed_governance_id": "dg-ab", "worker_ids": ["worker-a", "worker-b"], "governance_record_ids": ["fed-policy", "fed-authority-local"], "federation_id": "federation-ab"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["worker_count"] == 2
    assert session["continuity_summary"]["graph_continuity"]["distributed_execution_count"] == 2
    assert session["lineage"]["actor_worker_graph"]["workers"]

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "main",
        "continued_branch_id": "main",
        "governance_record_ids": ["fed-policy", "fed-authority-local"],
        "worker_ids": ["worker-a", "worker-b"],
        "distributed_execution_ids": ["dx-a", "dx-b"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["worker_ids"] == ["worker-a", "worker-b"]
    json.dumps(replay_session, sort_keys=True, default=str)

    broken_worker = dict(session)
    broken_worker["lineage"] = dict(session["lineage"])
    broken_worker["lineage"]["actor_worker_graph"] = dict(session["lineage"]["actor_worker_graph"])
    broken_worker["lineage"]["actor_worker_graph"]["distributed_executions"] = [dict(item) for item in session["lineage"]["actor_worker_graph"]["distributed_executions"]]
    broken_worker["lineage"]["actor_worker_graph"]["distributed_executions"][0]["worker_id"] = "missing-worker"
    broken_worker_summary = manager.continuity_summary(broken_worker)
    assert broken_worker_summary["ok"] is False
    assert "worker_lineage_mismatch" in broken_worker_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["worker_ids"] = ["unrelated-worker"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_worker_lineage_mismatch" in broken_replay_summary["breaks"]

    broken_authority = dict(session)
    broken_authority["lineage"] = dict(session["lineage"])
    broken_authority["lineage"]["actor_worker_graph"] = dict(session["lineage"]["actor_worker_graph"])
    broken_authority["lineage"]["actor_worker_graph"]["federated_authority"] = [dict(item) for item in session["lineage"]["actor_worker_graph"]["federated_authority"]]
    broken_authority["lineage"]["actor_worker_graph"]["federated_authority"][0]["worker_id"] = "missing-worker"
    broken_authority_summary = manager.continuity_summary(broken_authority)
    assert broken_authority_summary["ok"] is False
    assert "federated_authority_mismatch" in broken_authority_summary["breaks"]

    broken_recovery = dict(session)
    broken_recovery["lineage"] = dict(session["lineage"])
    broken_recovery["lineage"]["actor_worker_graph"] = dict(session["lineage"]["actor_worker_graph"])
    broken_recovery["lineage"]["actor_worker_graph"]["distributed_recoveries"] = [dict(item) for item in session["lineage"]["actor_worker_graph"]["distributed_recoveries"]]
    broken_recovery["lineage"]["actor_worker_graph"]["distributed_recoveries"][0]["source_execution_id"] = "missing-execution"
    broken_recovery_summary = manager.continuity_summary(broken_recovery)
    assert broken_recovery_summary["ok"] is False
    assert "distributed_recovery_unrelated_execution" in broken_recovery_summary["breaks"]

    broken_governance = dict(session)
    broken_governance["lineage"] = dict(session["lineage"])
    broken_governance["lineage"]["actor_worker_graph"] = dict(session["lineage"]["actor_worker_graph"])
    broken_governance["lineage"]["actor_worker_graph"]["distributed_governance"] = [dict(item) for item in session["lineage"]["actor_worker_graph"]["distributed_governance"]]
    broken_governance["lineage"]["actor_worker_graph"]["distributed_governance"][0]["worker_ids"] = ["stale-worker"]
    broken_governance_summary = manager.continuity_summary(broken_governance)
    assert broken_governance_summary["ok"] is False
    assert "distributed_governance_stale_worker" in broken_governance_summary["breaks"]


def test_workflow_runtime_arbitration_federated_governance_consensus_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-arbitration", "steps": []}
    state = {"task_id": "wf-arbitration", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-arbitration", "goal": "arbitrate workers"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, node in (
        (2, {"node_id": "arb-root", "branch_id": "main"}),
        (3, {"node_id": "arb-target", "branch_id": "main", "parent_node_id": "arb-root"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    for tick, worker in (
        (4, {"worker_id": "authority-a", "actor_id": "actor-a", "authority_scope": "governance"}),
        (5, {"worker_id": "authority-b", "actor_id": "actor-b", "authority_scope": "governance"}),
    ):
        session = manager.attach_actor_worker_record(task=task, state=state, worker=worker, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_worker_federation_record(
        task=task,
        state=state,
        federation={"federation_id": "federation-arb", "worker_ids": ["authority-a", "authority-b"], "coordinator_worker_id": "authority-a"},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "decision-a", "worker_id": "authority-a", "federation_id": "federation-arb", "target_node_id": "arb-target", "decision": "allow"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "decision-b", "worker_id": "authority-b", "federation_id": "federation-arb", "target_node_id": "arb-target", "decision": "block"},
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_arbitration_decision_record(
        task=task,
        state=state,
        arbitration={"arbitration_id": "arbitration-ab", "conflicting_decision_ids": ["decision-a", "decision-b"], "worker_ids": ["authority-a", "authority-b"], "federation_id": "federation-arb", "target_node_id": "arb-target", "decision": "review"},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_quorum_record(
        task=task,
        state=state,
        quorum={"quorum_id": "quorum-ab", "authority_worker_ids": ["authority-a", "authority-b"], "federation_id": "federation-arb", "threshold": 2},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_consensus_vote_record(
        task=task,
        state=state,
        vote={"vote_id": "vote-a", "quorum_id": "quorum-ab", "worker_id": "authority-a", "federation_id": "federation-arb", "vote": "accept", "accepted": True},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_consensus_vote_record(
        task=task,
        state=state,
        vote={"vote_id": "vote-b", "quorum_id": "quorum-ab", "worker_id": "authority-b", "federation_id": "federation-arb", "vote": "accept", "accepted": True},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_federated_consensus_record(
        task=task,
        state=state,
        consensus={"consensus_id": "consensus-ab", "arbitration_id": "arbitration-ab", "quorum_id": "quorum-ab", "vote_ids": ["vote-a", "vote-b"], "required_vote_ids": ["vote-a", "vote-b"], "worker_ids": ["authority-a", "authority-b"], "federation_id": "federation-arb", "decision": "accepted"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_replay_reconciliation_record(
        task=task,
        state=state,
        reconciliation={"replay_reconciliation_id": "replay-rec-ab", "consensus_id": "consensus-ab", "arbitration_id": "arbitration-ab", "vote_ids": ["vote-a", "vote-b"]},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_federated_governance_decision_record(
        task=task,
        state=state,
        governance={"governance_decision_id": "gov-decision-ab", "consensus_id": "consensus-ab", "arbitration_id": "arbitration-ab", "worker_ids": ["authority-a", "authority-b"], "federation_id": "federation-arb", "decision": "resume"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["arbitration_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["authority_quorum_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["consensus_vote_count"] == 2
    assert session["continuity_summary"]["graph_continuity"]["federated_consensus_count"] == 1
    assert session["lineage"]["federated_consensus_graph"]["consensus"]
    json.dumps(session, sort_keys=True, default=str)

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "main",
        "continued_branch_id": "main",
        "worker_ids": ["authority-a", "authority-b"],
        "consensus_ids": ["consensus-ab"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["consensus_ids"] == ["consensus-ab"]

    broken_arbitration = dict(session)
    broken_arbitration["lineage"] = dict(session["lineage"])
    broken_arbitration["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_arbitration["lineage"]["federated_consensus_graph"]["arbitrations"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["arbitrations"]]
    broken_arbitration["lineage"]["federated_consensus_graph"]["arbitrations"][0]["conflicting_decision_ids"] = ["decision-a"]
    broken_arbitration_summary = manager.continuity_summary(broken_arbitration)
    assert broken_arbitration_summary["ok"] is False
    assert "arbitration_without_conflicting_decision_parents" in broken_arbitration_summary["breaks"]

    broken_quorum = dict(session)
    broken_quorum["lineage"] = dict(session["lineage"])
    broken_quorum["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_quorum["lineage"]["federated_consensus_graph"]["quorums"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["quorums"]]
    broken_quorum["lineage"]["federated_consensus_graph"]["quorums"][0]["authority_worker_ids"] = ["authority-a", "missing-worker"]
    broken_quorum_summary = manager.continuity_summary(broken_quorum)
    assert broken_quorum_summary["ok"] is False
    assert "quorum_missing_authority_worker" in broken_quorum_summary["breaks"]

    broken_vote = dict(session)
    broken_vote["lineage"] = dict(session["lineage"])
    broken_vote["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_vote["lineage"]["federated_consensus_graph"]["votes"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["votes"]]
    broken_vote["lineage"]["federated_consensus_graph"]["votes"][0]["quorum_id"] = "missing-quorum"
    broken_vote_summary = manager.continuity_summary(broken_vote)
    assert broken_vote_summary["ok"] is False
    assert "vote_not_linked_to_quorum" in broken_vote_summary["breaks"]

    broken_consensus_parent = dict(session)
    broken_consensus_parent["lineage"] = dict(session["lineage"])
    broken_consensus_parent["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_consensus_parent["lineage"]["federated_consensus_graph"]["consensus"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["consensus"]]
    broken_consensus_parent["lineage"]["federated_consensus_graph"]["consensus"][0]["arbitration_id"] = "missing-arbitration"
    broken_consensus_parent_summary = manager.continuity_summary(broken_consensus_parent)
    assert broken_consensus_parent_summary["ok"] is False
    assert "consensus_missing_arbitration_parent" in broken_consensus_parent_summary["breaks"]

    broken_consensus_vote = dict(session)
    broken_consensus_vote["lineage"] = dict(session["lineage"])
    broken_consensus_vote["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_consensus_vote["lineage"]["federated_consensus_graph"]["consensus"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["consensus"]]
    broken_consensus_vote["lineage"]["federated_consensus_graph"]["consensus"][0]["required_vote_ids"] = ["vote-a", "missing-vote"]
    broken_consensus_vote_summary = manager.continuity_summary(broken_consensus_vote)
    assert broken_consensus_vote_summary["ok"] is False
    assert "consensus_missing_required_vote" in broken_consensus_vote_summary["breaks"]

    broken_reconciliation = dict(session)
    broken_reconciliation["lineage"] = dict(session["lineage"])
    broken_reconciliation["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_reconciliation["lineage"]["federated_consensus_graph"]["replay_reconciliations"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["replay_reconciliations"]]
    broken_reconciliation["lineage"]["federated_consensus_graph"]["replay_reconciliations"][0]["consensus_lineage_hash"] = "stale"
    broken_reconciliation_summary = manager.continuity_summary(broken_reconciliation)
    assert broken_reconciliation_summary["ok"] is False
    assert "replay_reconciliation_stale_consensus_lineage" in broken_reconciliation_summary["breaks"]

    broken_governance = dict(session)
    broken_governance["lineage"] = dict(session["lineage"])
    broken_governance["lineage"]["federated_consensus_graph"] = dict(session["lineage"]["federated_consensus_graph"])
    broken_governance["lineage"]["federated_consensus_graph"]["governance_decisions"] = [dict(item) for item in session["lineage"]["federated_consensus_graph"]["governance_decisions"]]
    broken_governance["lineage"]["federated_consensus_graph"]["governance_decisions"][0]["worker_ids"] = ["unrelated-worker"]
    broken_governance_summary = manager.continuity_summary(broken_governance)
    assert broken_governance_summary["ok"] is False
    assert "governance_decision_unrelated_worker_lineage" in broken_governance_summary["breaks"]


def test_workflow_runtime_self_observability_self_healing_governance_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-self-healing", "steps": []}
    state = {"task_id": "wf-self-healing", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-self-healing", "goal": "self heal governance"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, node in (
        (2, {"node_id": "self-root", "branch_id": "main"}),
        (3, {"node_id": "self-target", "branch_id": "main", "parent_node_id": "self-root"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "self-policy", "target_node_id": "self-target", "branch_id": "main", "allowed": False, "decision": "review_required"},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"authority_id": "self-authority", "target_node_id": "self-target", "branch_id": "main", "execution_owner": "TaskRunner"},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_review_required_record(
        task=task,
        state=state,
        review={"review_id": "self-review", "policy_decision_id": "self-policy", "target_node_id": "self-target", "branch_id": "main"},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_approval_record(
        task=task,
        state=state,
        approval={"approval_id": "self-approval", "review_id": "self-review", "policy_decision_id": "self-policy", "target_node_id": "self-target", "branch_id": "main"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session

    for tick, worker in (
        (8, {"worker_id": "self-worker-a", "actor_id": "self-a", "authority_scope": "governance"}),
        (9, {"worker_id": "self-worker-b", "actor_id": "self-b", "authority_scope": "governance"}),
    ):
        session = manager.attach_actor_worker_record(task=task, state=state, worker=worker, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_worker_federation_record(
        task=task,
        state=state,
        federation={"federation_id": "self-federation", "worker_ids": ["self-worker-a", "self-worker-b"], "coordinator_worker_id": "self-worker-a"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "self-decision-a", "worker_id": "self-worker-a", "federation_id": "self-federation", "target_node_id": "self-target", "decision": "repair"},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "self-decision-b", "worker_id": "self-worker-b", "federation_id": "self-federation", "target_node_id": "self-target", "decision": "hold"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_arbitration_decision_record(
        task=task,
        state=state,
        arbitration={"arbitration_id": "self-arbitration", "conflicting_decision_ids": ["self-decision-a", "self-decision-b"], "worker_ids": ["self-worker-a", "self-worker-b"], "federation_id": "self-federation", "target_node_id": "self-target", "decision": "repair"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_quorum_record(
        task=task,
        state=state,
        quorum={"quorum_id": "self-quorum", "authority_worker_ids": ["self-worker-a", "self-worker-b"], "federation_id": "self-federation", "threshold": 2},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    for tick, vote in (
        (15, {"vote_id": "self-vote-a", "quorum_id": "self-quorum", "worker_id": "self-worker-a", "federation_id": "self-federation", "vote": "accept"}),
        (16, {"vote_id": "self-vote-b", "quorum_id": "self-quorum", "worker_id": "self-worker-b", "federation_id": "self-federation", "vote": "accept"}),
    ):
        session = manager.attach_consensus_vote_record(task=task, state=state, vote=vote, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_federated_consensus_record(
        task=task,
        state=state,
        consensus={"consensus_id": "self-consensus", "arbitration_id": "self-arbitration", "quorum_id": "self-quorum", "vote_ids": ["self-vote-a", "self-vote-b"], "required_vote_ids": ["self-vote-a", "self-vote-b"], "worker_ids": ["self-worker-a", "self-worker-b"], "federation_id": "self-federation", "decision": "repair"},
        current_tick=17,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_runtime_self_observability_record(
        task=task,
        state=state,
        observability={"observability_id": "self-observe", "target_node_id": "self-target", "signal": "governance_drift", "severity": "warning"},
        current_tick=18,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_audit_lineage_record(
        task=task,
        state=state,
        audit={"audit_id": "self-audit", "observability_id": "self-observe", "target_node_id": "self-target", "rule_id": "runtime_constitution", "finding": "drift_detected"},
        current_tick=19,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_self_diagnosis_record(
        task=task,
        state=state,
        diagnosis={"diagnosis_id": "self-diagnosis", "audit_id": "self-audit", "observability_id": "self-observe", "target_node_id": "self-target", "diagnosis": "authority_drift"},
        current_tick=20,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_self_repair_governance_record(
        task=task,
        state=state,
        repair={"self_repair_id": "self-repair", "diagnosis_id": "self-diagnosis", "audit_id": "self-audit", "observability_id": "self-observe", "authority_id": "self-authority", "approval_id": "self-approval", "consensus_id": "self-consensus", "repair_action": "stabilize_authority"},
        current_tick=21,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_self_healing_replay_recovery_record(
        task=task,
        state=state,
        recovery={"self_healing_recovery_id": "self-healing", "self_repair_id": "self-repair", "diagnosis_id": "self-diagnosis", "recovery_action": "replay_stabilized_lineage"},
        current_tick=22,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_adaptive_governance_stabilization_record(
        task=task,
        state=state,
        stabilization={"stabilization_id": "self-stabilization", "self_healing_recovery_id": "self-healing", "self_repair_id": "self-repair", "stabilization": "authority_stable"},
        current_tick=23,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["self_observability_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["constitutional_audit_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["self_diagnosis_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["self_repair_governance_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["self_healing_recovery_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["adaptive_stabilization_count"] == 1
    json.dumps(session, sort_keys=True, default=str)

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "main",
        "continued_branch_id": "main",
        "consensus_ids": ["self-consensus"],
        "self_healing_recovery_ids": ["self-healing"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["self_healing_recovery_ids"] == ["self-healing"]

    broken_audit = dict(session)
    broken_audit["lineage"] = dict(session["lineage"])
    broken_audit["lineage"]["self_healing_governance_graph"] = dict(session["lineage"]["self_healing_governance_graph"])
    broken_audit["lineage"]["self_healing_governance_graph"]["audits"] = [dict(item) for item in session["lineage"]["self_healing_governance_graph"]["audits"]]
    broken_audit["lineage"]["self_healing_governance_graph"]["audits"][0]["observability_id"] = "missing-observe"
    broken_audit_summary = manager.continuity_summary(broken_audit)
    assert broken_audit_summary["ok"] is False
    assert "audit_without_observability_parent" in broken_audit_summary["breaks"]

    broken_diagnosis = dict(session)
    broken_diagnosis["lineage"] = dict(session["lineage"])
    broken_diagnosis["lineage"]["self_healing_governance_graph"] = dict(session["lineage"]["self_healing_governance_graph"])
    broken_diagnosis["lineage"]["self_healing_governance_graph"]["diagnoses"] = [dict(item) for item in session["lineage"]["self_healing_governance_graph"]["diagnoses"]]
    broken_diagnosis["lineage"]["self_healing_governance_graph"]["diagnoses"][0]["audit_id"] = "missing-audit"
    broken_diagnosis_summary = manager.continuity_summary(broken_diagnosis)
    assert broken_diagnosis_summary["ok"] is False
    assert "diagnosis_without_audit_observability_parent" in broken_diagnosis_summary["breaks"]

    broken_repair = dict(session)
    broken_repair["lineage"] = dict(session["lineage"])
    broken_repair["lineage"]["self_healing_governance_graph"] = dict(session["lineage"]["self_healing_governance_graph"])
    broken_repair["lineage"]["self_healing_governance_graph"]["self_repairs"] = [dict(item) for item in session["lineage"]["self_healing_governance_graph"]["self_repairs"]]
    broken_repair["lineage"]["self_healing_governance_graph"]["self_repairs"][0]["consensus_id"] = "missing-consensus"
    broken_repair_summary = manager.continuity_summary(broken_repair)
    assert broken_repair_summary["ok"] is False
    assert "self_repair_governance_missing_authority_lineage" in broken_repair_summary["breaks"]

    broken_recovery = dict(session)
    broken_recovery["lineage"] = dict(session["lineage"])
    broken_recovery["lineage"]["self_healing_governance_graph"] = dict(session["lineage"]["self_healing_governance_graph"])
    broken_recovery["lineage"]["self_healing_governance_graph"]["recoveries"] = [dict(item) for item in session["lineage"]["self_healing_governance_graph"]["recoveries"]]
    broken_recovery["lineage"]["self_healing_governance_graph"]["recoveries"][0]["self_repair_id"] = "missing-repair"
    broken_recovery_summary = manager.continuity_summary(broken_recovery)
    assert broken_recovery_summary["ok"] is False
    assert "self_healing_recovery_without_repair_parent" in broken_recovery_summary["breaks"]

    broken_stabilization = dict(session)
    broken_stabilization["lineage"] = dict(session["lineage"])
    broken_stabilization["lineage"]["self_healing_governance_graph"] = dict(session["lineage"]["self_healing_governance_graph"])
    broken_stabilization["lineage"]["self_healing_governance_graph"]["stabilizations"] = [dict(item) for item in session["lineage"]["self_healing_governance_graph"]["stabilizations"]]
    broken_stabilization["lineage"]["self_healing_governance_graph"]["stabilizations"][0]["self_healing_recovery_id"] = "missing-recovery"
    broken_stabilization_summary = manager.continuity_summary(broken_stabilization)
    assert broken_stabilization_summary["ok"] is False
    assert "stabilization_without_recovery_parent" in broken_stabilization_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["self_healing_recovery_ids"] = ["stale-healing"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_stale_self_healing_lineage" in broken_replay_summary["breaks"]


def test_workflow_runtime_constitutional_preservation_catastrophic_recovery_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-preservation", "steps": []}
    state = {"task_id": "wf-preservation", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-preservation", "goal": "preserve constitution"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, node in (
        (2, {"node_id": "preserve-root", "branch_id": "main"}),
        (3, {"node_id": "constitution-node", "branch_id": "main", "parent_node_id": "preserve-root"}),
        (4, {"node_id": "mutation-node", "branch_id": "main", "parent_node_id": "constitution-node"}),
        (5, {"node_id": "verify-node", "branch_id": "main", "parent_node_id": "mutation-node", "phase": "verify"}),
        (6, {"node_id": "rollback-node", "branch_id": "main", "parent_node_id": "verify-node", "phase": "rollback_retry"}),
        (7, {"node_id": "recovery-node", "branch_id": "main", "parent_node_id": "rollback-node", "phase": "rollback_retry"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "preserve-policy", "target_node_id": "constitution-node", "branch_id": "main", "allowed": False, "decision": "preserve"},
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"authority_id": "preserve-authority", "target_node_id": "constitution-node", "branch_id": "main", "execution_owner": "TaskRunner"},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_review_required_record(
        task=task,
        state=state,
        review={"review_id": "preserve-review", "policy_decision_id": "preserve-policy", "target_node_id": "constitution-node", "branch_id": "main"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_approval_record(
        task=task,
        state=state,
        approval={"approval_id": "preserve-approval", "review_id": "preserve-review", "policy_decision_id": "preserve-policy", "target_node_id": "constitution-node", "branch_id": "main"},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitution_enforcement_record(
        task=task,
        state=state,
        enforcement={"enforcement_id": "constitution-enforcement", "target_node_id": "constitution-node", "branch_id": "main", "rule_id": "runtime_constitution"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_mutation_transaction(
        task=task,
        state=state,
        mutation={"mutation_transaction_id": "constitutional-change", "node_id": "mutation-node", "branch_id": "main", "mutation_type": "constitutional_change"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_mutation_verify_record(
        task=task,
        state=state,
        verify={"mutation_verify_id": "constitutional-change-verify", "mutation_transaction_id": "constitutional-change", "verify_node_id": "verify-node", "branch_id": "main", "ok": False},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_rollback_graph_node(
        task=task,
        state=state,
        rollback={"rollback_id": "constitutional-rollback", "rollback_node_id": "rollback-node", "mutation_transaction_id": "constitutional-change", "mutation_verify_id": "constitutional-change-verify", "branch_id": "main", "retry_node_id": "recovery-node"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_recovery_dependency(
        task=task,
        state=state,
        dependency={"recovery_dependency_id": "constitutional-recovery-dependency", "source_node_id": "rollback-node", "target_node_id": "recovery-node", "branch_id": "main"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session

    for tick, worker in (
        (17, {"worker_id": "preserve-worker-a", "actor_id": "preserve-a", "authority_scope": "governance"}),
        (18, {"worker_id": "preserve-worker-b", "actor_id": "preserve-b", "authority_scope": "governance"}),
    ):
        session = manager.attach_actor_worker_record(task=task, state=state, worker=worker, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_worker_federation_record(
        task=task,
        state=state,
        federation={"federation_id": "preserve-federation", "worker_ids": ["preserve-worker-a", "preserve-worker-b"], "coordinator_worker_id": "preserve-worker-a"},
        current_tick=19,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "preserve-decision-a", "worker_id": "preserve-worker-a", "federation_id": "preserve-federation", "target_node_id": "constitution-node", "decision": "rollback"},
        current_tick=20,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "preserve-decision-b", "worker_id": "preserve-worker-b", "federation_id": "preserve-federation", "target_node_id": "constitution-node", "decision": "hold"},
        current_tick=21,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_arbitration_decision_record(
        task=task,
        state=state,
        arbitration={"arbitration_id": "preserve-arbitration", "conflicting_decision_ids": ["preserve-decision-a", "preserve-decision-b"], "worker_ids": ["preserve-worker-a", "preserve-worker-b"], "federation_id": "preserve-federation", "target_node_id": "constitution-node", "decision": "rollback"},
        current_tick=22,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_quorum_record(
        task=task,
        state=state,
        quorum={"quorum_id": "preserve-quorum", "authority_worker_ids": ["preserve-worker-a", "preserve-worker-b"], "federation_id": "preserve-federation", "threshold": 2},
        current_tick=23,
    )
    state["workflow_runtime_session"] = session
    for tick, vote in (
        (24, {"vote_id": "preserve-vote-a", "quorum_id": "preserve-quorum", "worker_id": "preserve-worker-a", "federation_id": "preserve-federation", "vote": "accept"}),
        (25, {"vote_id": "preserve-vote-b", "quorum_id": "preserve-quorum", "worker_id": "preserve-worker-b", "federation_id": "preserve-federation", "vote": "accept"}),
    ):
        session = manager.attach_consensus_vote_record(task=task, state=state, vote=vote, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_federated_consensus_record(
        task=task,
        state=state,
        consensus={"consensus_id": "preserve-consensus", "arbitration_id": "preserve-arbitration", "quorum_id": "preserve-quorum", "vote_ids": ["preserve-vote-a", "preserve-vote-b"], "required_vote_ids": ["preserve-vote-a", "preserve-vote-b"], "worker_ids": ["preserve-worker-a", "preserve-worker-b"], "federation_id": "preserve-federation", "decision": "rollback"},
        current_tick=26,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_runtime_self_observability_record(
        task=task,
        state=state,
        observability={"observability_id": "preserve-observe", "target_node_id": "constitution-node", "signal": "catastrophic_constitution_drift", "severity": "critical"},
        current_tick=27,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_preservation_record(
        task=task,
        state=state,
        preservation={"preservation_id": "preservation-record", "constitution_node_id": "constitution-node", "governance_record_id": "constitution-enforcement", "enforcement_id": "constitution-enforcement", "policy_decision_id": "preserve-policy"},
        current_tick=28,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_self_preservation_decision_record(
        task=task,
        state=state,
        decision={"self_preservation_decision_id": "self-preservation", "preservation_id": "preservation-record", "observability_id": "preserve-observe", "policy_decision_id": "preserve-policy", "authority_id": "preserve-authority", "decision": "preserve"},
        current_tick=29,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_catastrophic_failure_record(
        task=task,
        state=state,
        failure={"catastrophic_failure_id": "catastrophic-failure", "failure_node_id": "constitution-node", "governance_record_id": "constitution-enforcement", "failure_classification": "constitutional_corruption"},
        current_tick=30,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_catastrophic_recovery_lineage_record(
        task=task,
        state=state,
        recovery={"catastrophic_recovery_id": "catastrophic-recovery", "catastrophic_failure_id": "catastrophic-failure", "rollback_id": "constitutional-rollback", "recovery_dependency_id": "constitutional-recovery-dependency", "recovery_node_id": "recovery-node"},
        current_tick=31,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_rollback_arbitration_record(
        task=task,
        state=state,
        arbitration={"constitutional_rollback_arbitration_id": "constitutional-rollback-arbitration", "consensus_id": "preserve-consensus", "quorum_id": "preserve-quorum", "failed_constitutional_change_id": "preservation-record", "rollback_id": "constitutional-rollback", "decision": "rollback"},
        current_tick=32,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_adaptive_constitutional_stabilization_record(
        task=task,
        state=state,
        stabilization={"constitutional_stabilization_id": "constitutional-stabilization", "catastrophic_recovery_id": "catastrophic-recovery", "preservation_id": "preservation-record", "stabilization": "constitution_stable"},
        current_tick=33,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_survivability_continuity_record(
        task=task,
        state=state,
        survivability={"survivability_id": "survivability-record", "preservation_id": "preservation-record", "catastrophic_recovery_id": "catastrophic-recovery", "constitutional_stabilization_id": "constitutional-stabilization", "status": "survivable"},
        current_tick=34,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["constitutional_preservation_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["catastrophic_failure_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["catastrophic_recovery_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["survivability_count"] == 1
    json.dumps(session, sort_keys=True, default=str)

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "main",
        "continued_branch_id": "main",
        "preservation_ids": ["preservation-record"],
        "consensus_ids": ["preserve-consensus"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["preservation_ids"] == ["preservation-record"]

    broken_preservation = dict(session)
    broken_preservation["lineage"] = dict(session["lineage"])
    broken_preservation["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_preservation["lineage"]["constitutional_preservation_graph"]["preservations"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["preservations"]]
    broken_preservation["lineage"]["constitutional_preservation_graph"]["preservations"][0]["constitution_node_id"] = "missing-node"
    broken_preservation_summary = manager.continuity_summary(broken_preservation)
    assert broken_preservation_summary["ok"] is False
    assert "preservation_without_constitution_parent" in broken_preservation_summary["breaks"]

    broken_self_preservation = dict(session)
    broken_self_preservation["lineage"] = dict(session["lineage"])
    broken_self_preservation["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_self_preservation["lineage"]["constitutional_preservation_graph"]["self_preservation_decisions"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["self_preservation_decisions"]]
    broken_self_preservation["lineage"]["constitutional_preservation_graph"]["self_preservation_decisions"][0]["authority_id"] = "missing-authority"
    broken_self_preservation_summary = manager.continuity_summary(broken_self_preservation)
    assert broken_self_preservation_summary["ok"] is False
    assert "self_preservation_missing_observability_authority" in broken_self_preservation_summary["breaks"]

    broken_recovery = dict(session)
    broken_recovery["lineage"] = dict(session["lineage"])
    broken_recovery["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_recovery["lineage"]["constitutional_preservation_graph"]["catastrophic_recoveries"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["catastrophic_recoveries"]]
    broken_recovery["lineage"]["constitutional_preservation_graph"]["catastrophic_recoveries"][0]["catastrophic_failure_id"] = "missing-failure"
    broken_recovery_summary = manager.continuity_summary(broken_recovery)
    assert broken_recovery_summary["ok"] is False
    assert "catastrophic_recovery_without_failure_parent" in broken_recovery_summary["breaks"]

    broken_arbitration = dict(session)
    broken_arbitration["lineage"] = dict(session["lineage"])
    broken_arbitration["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_arbitration["lineage"]["constitutional_preservation_graph"]["rollback_arbitrations"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["rollback_arbitrations"]]
    broken_arbitration["lineage"]["constitutional_preservation_graph"]["rollback_arbitrations"][0]["quorum_id"] = "missing-quorum"
    broken_arbitration_summary = manager.continuity_summary(broken_arbitration)
    assert broken_arbitration_summary["ok"] is False
    assert "constitutional_rollback_arbitration_missing_consensus_quorum" in broken_arbitration_summary["breaks"]

    broken_stabilization = dict(session)
    broken_stabilization["lineage"] = dict(session["lineage"])
    broken_stabilization["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_stabilization["lineage"]["constitutional_preservation_graph"]["stabilizations"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["stabilizations"]]
    broken_stabilization["lineage"]["constitutional_preservation_graph"]["stabilizations"][0]["catastrophic_recovery_id"] = "missing-recovery"
    broken_stabilization_summary = manager.continuity_summary(broken_stabilization)
    assert broken_stabilization_summary["ok"] is False
    assert "constitutional_stabilization_without_recovery_parent" in broken_stabilization_summary["breaks"]

    broken_survivability = dict(session)
    broken_survivability["lineage"] = dict(session["lineage"])
    broken_survivability["lineage"]["constitutional_preservation_graph"] = dict(session["lineage"]["constitutional_preservation_graph"])
    broken_survivability["lineage"]["constitutional_preservation_graph"]["survivability"] = [dict(item) for item in session["lineage"]["constitutional_preservation_graph"]["survivability"]]
    broken_survivability["lineage"]["constitutional_preservation_graph"]["survivability"][0]["constitutional_stabilization_id"] = "missing-stabilization"
    broken_survivability_summary = manager.continuity_summary(broken_survivability)
    assert broken_survivability_summary["ok"] is False
    assert "survivability_without_preservation_recovery_stabilization" in broken_survivability_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["preservation_ids"] = ["stale-preservation"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_stale_constitutional_preservation_lineage" in broken_replay_summary["breaks"]


def test_workflow_runtime_autonomous_constitutional_evolution_fork_merge_governance_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-evolution", "steps": []}
    state = {"task_id": "wf-evolution", "status": "running", "steps": [], "current_branch_id": "main"}

    session = manager.start_from_intent(intent={"task_id": "wf-evolution", "goal": "evolve constitution"}, task=task, state=state, current_tick=1)
    state["workflow_runtime_session"] = session
    session_id = session["session_id"]

    for tick, node in (
        (2, {"node_id": "evo-root", "branch_id": "main"}),
        (3, {"node_id": "evo-constitution", "branch_id": "main", "parent_node_id": "evo-root"}),
        (4, {"node_id": "evo-rollback", "branch_id": "main", "parent_node_id": "evo-constitution", "phase": "rollback_retry"}),
        (5, {"node_id": "evo-recovery", "branch_id": "main", "parent_node_id": "evo-rollback", "phase": "rollback_retry"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "evo-policy", "target_node_id": "evo-constitution", "branch_id": "main", "allowed": True, "decision": "evolve"},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"authority_id": "evo-authority", "target_node_id": "evo-constitution", "branch_id": "main", "execution_owner": "TaskRunner"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitution_enforcement_record(
        task=task,
        state=state,
        enforcement={"enforcement_id": "evo-enforcement", "target_node_id": "evo-constitution", "branch_id": "main", "rule_id": "runtime_constitution"},
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_preservation_record(
        task=task,
        state=state,
        preservation={"preservation_id": "evo-preservation", "constitution_node_id": "evo-constitution", "governance_record_id": "evo-enforcement", "enforcement_id": "evo-enforcement", "policy_decision_id": "evo-policy"},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_mutation_transaction(
        task=task,
        state=state,
        mutation={"mutation_transaction_id": "evo-mutation", "node_id": "evo-constitution", "branch_id": "main", "mutation_type": "constitutional_evolution"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_mutation_verify_record(
        task=task,
        state=state,
        verify={"mutation_verify_id": "evo-verify", "mutation_transaction_id": "evo-mutation", "verify_node_id": "evo-constitution", "branch_id": "main", "ok": False},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_rollback_graph_node(
        task=task,
        state=state,
        rollback={"rollback_id": "evo-rollback-id", "rollback_node_id": "evo-rollback", "mutation_transaction_id": "evo-mutation", "mutation_verify_id": "evo-verify", "branch_id": "main", "retry_node_id": "evo-recovery"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_recovery_dependency(
        task=task,
        state=state,
        dependency={"recovery_dependency_id": "evo-recovery-dependency", "source_node_id": "evo-rollback", "target_node_id": "evo-recovery", "branch_id": "main"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_catastrophic_failure_record(
        task=task,
        state=state,
        failure={"catastrophic_failure_id": "evo-failure", "failure_node_id": "evo-constitution", "governance_record_id": "evo-enforcement"},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_catastrophic_recovery_lineage_record(
        task=task,
        state=state,
        recovery={"catastrophic_recovery_id": "evo-recovery-record", "catastrophic_failure_id": "evo-failure", "rollback_id": "evo-rollback-id", "recovery_dependency_id": "evo-recovery-dependency", "recovery_node_id": "evo-recovery"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_adaptive_constitutional_stabilization_record(
        task=task,
        state=state,
        stabilization={"constitutional_stabilization_id": "evo-constitutional-stabilization", "catastrophic_recovery_id": "evo-recovery-record", "preservation_id": "evo-preservation"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session

    for tick, worker in (
        (17, {"worker_id": "evo-worker-a", "actor_id": "evo-a", "authority_scope": "governance"}),
        (18, {"worker_id": "evo-worker-b", "actor_id": "evo-b", "authority_scope": "governance"}),
    ):
        session = manager.attach_actor_worker_record(task=task, state=state, worker=worker, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_worker_federation_record(
        task=task,
        state=state,
        federation={"federation_id": "evo-federation", "worker_ids": ["evo-worker-a", "evo-worker-b"], "coordinator_worker_id": "evo-worker-a"},
        current_tick=19,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "evo-decision-a", "worker_id": "evo-worker-a", "federation_id": "evo-federation", "target_node_id": "evo-constitution", "decision": "merge"},
        current_tick=20,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_worker_decision_record(
        task=task,
        state=state,
        decision={"worker_decision_id": "evo-decision-b", "worker_id": "evo-worker-b", "federation_id": "evo-federation", "target_node_id": "evo-constitution", "decision": "review"},
        current_tick=21,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_arbitration_decision_record(
        task=task,
        state=state,
        arbitration={"arbitration_id": "evo-arbitration", "conflicting_decision_ids": ["evo-decision-a", "evo-decision-b"], "worker_ids": ["evo-worker-a", "evo-worker-b"], "federation_id": "evo-federation", "target_node_id": "evo-constitution", "decision": "merge"},
        current_tick=22,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_authority_quorum_record(
        task=task,
        state=state,
        quorum={"quorum_id": "evo-quorum", "authority_worker_ids": ["evo-worker-a", "evo-worker-b"], "federation_id": "evo-federation", "threshold": 2},
        current_tick=23,
    )
    state["workflow_runtime_session"] = session
    for tick, vote in (
        (24, {"vote_id": "evo-vote-a", "quorum_id": "evo-quorum", "worker_id": "evo-worker-a", "federation_id": "evo-federation", "vote": "accept"}),
        (25, {"vote_id": "evo-vote-b", "quorum_id": "evo-quorum", "worker_id": "evo-worker-b", "federation_id": "evo-federation", "vote": "accept"}),
    ):
        session = manager.attach_consensus_vote_record(task=task, state=state, vote=vote, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_federated_consensus_record(
        task=task,
        state=state,
        consensus={"consensus_id": "evo-consensus", "arbitration_id": "evo-arbitration", "quorum_id": "evo-quorum", "vote_ids": ["evo-vote-a", "evo-vote-b"], "required_vote_ids": ["evo-vote-a", "evo-vote-b"], "worker_ids": ["evo-worker-a", "evo-worker-b"], "federation_id": "evo-federation", "decision": "merge"},
        current_tick=26,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_autonomous_constitutional_evolution_record(
        task=task,
        state=state,
        evolution={"evolution_id": "evo-record", "policy_decision_id": "evo-policy", "preservation_id": "evo-preservation", "constitution_node_id": "evo-constitution", "proposal": "fork_and_merge"},
        current_tick=27,
    )
    state["workflow_runtime_session"] = session
    for tick, branch in (
        (28, {"branch_id": "evo-branch-a", "parent_branch_id": "main", "fork_node_id": "evo-constitution"}),
        (29, {"branch_id": "evo-branch-b", "parent_branch_id": "main", "fork_node_id": "evo-constitution"}),
    ):
        session = manager.create_branch_fork(task=task, state=state, branch=branch, current_tick=tick)
        state["workflow_runtime_session"] = session
    for tick, node in (
        (30, {"node_id": "evo-a-node", "branch_id": "evo-branch-a", "parent_node_id": "evo-constitution"}),
        (31, {"node_id": "evo-b-node", "branch_id": "evo-branch-b", "parent_node_id": "evo-constitution"}),
    ):
        session = manager.create_execution_graph_node(task=task, state=state, node=node, current_tick=tick)
        state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_fork_record(
        task=task,
        state=state,
        fork={"constitutional_fork_id": "evo-fork-a", "evolution_id": "evo-record", "preservation_id": "evo-preservation", "constitution_node_id": "evo-constitution", "branch_id": "evo-branch-a", "parent_branch_id": "main", "fork_node_id": "evo-constitution"},
        current_tick=32,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_fork_record(
        task=task,
        state=state,
        fork={"constitutional_fork_id": "evo-fork-b", "evolution_id": "evo-record", "preservation_id": "evo-preservation", "constitution_node_id": "evo-constitution", "branch_id": "evo-branch-b", "parent_branch_id": "main", "fork_node_id": "evo-constitution"},
        current_tick=33,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "evo-policy-a", "target_node_id": "evo-a-node", "branch_id": "evo-branch-a", "allowed": True, "decision": "accept_fork_a"},
        current_tick=34,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"policy_decision_id": "evo-policy-b", "target_node_id": "evo-b-node", "branch_id": "evo-branch-b", "allowed": True, "decision": "accept_fork_b"},
        current_tick=35,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_merge_arbitration_record(
        task=task,
        state=state,
        arbitration={"merge_arbitration_id": "evo-merge-arbitration", "source_branch_ids": ["evo-branch-a", "evo-branch-b"], "target_branch_id": "main", "quorum_id": "evo-quorum", "consensus_id": "evo-consensus", "decision": "merge"},
        current_tick=36,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_constitutional_merge_record(
        task=task,
        state=state,
        merge={"constitutional_merge_id": "evo-merge", "merge_arbitration_id": "evo-merge-arbitration", "source_branch_ids": ["evo-branch-a", "evo-branch-b"], "target_branch_id": "main", "merged_preservation_id": "evo-preservation"},
        current_tick=37,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_survivability_federation_continuity_record(
        task=task,
        state=state,
        survivability={"survivability_federation_id": "evo-survivability-federation", "constitutional_merge_id": "evo-merge", "federation_id": "evo-federation", "worker_ids": ["evo-worker-a", "evo-worker-b"]},
        current_tick=38,
    )
    state["workflow_runtime_session"] = session
    session = manager.attach_autonomous_governance_stabilization_loop_record(
        task=task,
        state=state,
        loop={"stabilization_loop_id": "evo-loop", "constitutional_merge_id": "evo-merge", "catastrophic_recovery_id": "evo-recovery-record", "constitutional_stabilization_id": "evo-constitutional-stabilization"},
        current_tick=39,
    )
    state["workflow_runtime_session"] = session

    assert session["continuity_summary"]["ok"] is True
    assert session["continuity_summary"]["graph_continuity"]["constitutional_evolution_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["constitutional_fork_count"] == 2
    assert session["continuity_summary"]["graph_continuity"]["constitutional_merge_arbitration_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["constitutional_merge_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["survivability_federation_count"] == 1
    assert session["continuity_summary"]["graph_continuity"]["governance_stabilization_loop_count"] == 1
    json.dumps(session, sort_keys=True, default=str)

    state["replay_continuation"] = {
        "source_session_id": session_id,
        "source_branch_id": "main",
        "continued_branch_id": "main",
        "evolution_ids": ["evo-record"],
        "preservation_ids": ["evo-preservation"],
    }
    replay = build_replayable_workflow_runtime_session(task=task, runtime_state={**state, "workflow_runtime_session": session})
    replay_session = replay["workflow_runtime_session"]
    assert replay_session["continuity_summary"]["ok"] is True
    assert replay_session["lineage"]["replay_continuation"]["evolution_ids"] == ["evo-record"]

    broken_evolution = dict(session)
    broken_evolution["lineage"] = dict(session["lineage"])
    broken_evolution["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_evolution["lineage"]["constitutional_evolution_graph"]["evolutions"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["evolutions"]]
    broken_evolution["lineage"]["constitutional_evolution_graph"]["evolutions"][0]["preservation_id"] = "missing-preservation"
    broken_evolution_summary = manager.continuity_summary(broken_evolution)
    assert broken_evolution_summary["ok"] is False
    assert "constitutional_evolution_missing_policy_preservation_lineage" in broken_evolution_summary["breaks"]

    broken_fork = dict(session)
    broken_fork["lineage"] = dict(session["lineage"])
    broken_fork["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_fork["lineage"]["constitutional_evolution_graph"]["forks"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["forks"]]
    broken_fork["lineage"]["constitutional_evolution_graph"]["forks"][0]["constitution_node_id"] = "missing-node"
    broken_fork_summary = manager.continuity_summary(broken_fork)
    assert broken_fork_summary["ok"] is False
    assert "constitutional_fork_without_active_parent" in broken_fork_summary["breaks"]

    broken_merge_arbitration = dict(session)
    broken_merge_arbitration["lineage"] = dict(session["lineage"])
    broken_merge_arbitration["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_merge_arbitration["lineage"]["constitutional_evolution_graph"]["merge_arbitrations"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["merge_arbitrations"]]
    broken_merge_arbitration["lineage"]["constitutional_evolution_graph"]["merge_arbitrations"][0]["source_branch_ids"] = ["evo-branch-a"]
    broken_merge_arbitration_summary = manager.continuity_summary(broken_merge_arbitration)
    assert broken_merge_arbitration_summary["ok"] is False
    assert "constitutional_merge_arbitration_missing_fork_branches" in broken_merge_arbitration_summary["breaks"]

    broken_merge = dict(session)
    broken_merge["lineage"] = dict(session["lineage"])
    broken_merge["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_merge["lineage"]["constitutional_evolution_graph"]["merges"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["merges"]]
    broken_merge["lineage"]["constitutional_evolution_graph"]["merges"][0]["merge_arbitration_id"] = "missing-arbitration"
    broken_merge_summary = manager.continuity_summary(broken_merge)
    assert broken_merge_summary["ok"] is False
    assert "constitutional_merge_without_arbitration_parent" in broken_merge_summary["breaks"]

    broken_survivability = dict(session)
    broken_survivability["lineage"] = dict(session["lineage"])
    broken_survivability["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_survivability["lineage"]["constitutional_evolution_graph"]["survivability_federations"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["survivability_federations"]]
    broken_survivability["lineage"]["constitutional_evolution_graph"]["survivability_federations"][0]["worker_ids"] = ["missing-worker"]
    broken_survivability_summary = manager.continuity_summary(broken_survivability)
    assert broken_survivability_summary["ok"] is False
    assert "survivability_federation_stale_worker_lineage" in broken_survivability_summary["breaks"]

    broken_loop = dict(session)
    broken_loop["lineage"] = dict(session["lineage"])
    broken_loop["lineage"]["constitutional_evolution_graph"] = dict(session["lineage"]["constitutional_evolution_graph"])
    broken_loop["lineage"]["constitutional_evolution_graph"]["stabilization_loops"] = [dict(item) for item in session["lineage"]["constitutional_evolution_graph"]["stabilization_loops"]]
    broken_loop["lineage"]["constitutional_evolution_graph"]["stabilization_loops"][0]["constitutional_merge_id"] = "missing-merge"
    broken_loop_summary = manager.continuity_summary(broken_loop)
    assert broken_loop_summary["ok"] is False
    assert "stabilization_loop_without_merge_recovery_lineage" in broken_loop_summary["breaks"]

    broken_replay = dict(replay_session)
    broken_replay["lineage"] = dict(replay_session["lineage"])
    broken_replay["lineage"]["replay_continuation"] = dict(replay_session["lineage"]["replay_continuation"])
    broken_replay["lineage"]["replay_continuation"]["evolution_ids"] = ["stale-evolution"]
    broken_replay_summary = manager.continuity_summary(broken_replay)
    assert broken_replay_summary["ok"] is False
    assert "replay_stale_constitutional_evolution_lineage" in broken_replay_summary["breaks"]


def test_runtime_constitutional_self_amendment_mutation_safety_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-self-amend", "steps": []}
    state = {"task_id": "wf-self-amend", "status": "running", "steps": []}

    session = manager.start_from_intent(
        intent={"task_id": "wf-self-amend", "goal": "safely amend runtime constitution"},
        task=task,
        state=state,
        current_tick=1,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_execution_graph_node_record(
        task=task,
        state=state,
        node={"node_id": "constitution-node", "label": "active constitution", "node_type": "constitution"},
        current_tick=2,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"target_node_id": "constitution-node", "policy_id": "runtime-constitution-policy", "allowed": True, "decision": "allow"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    policy_id = session["lineage"]["governance_state_graph"]["policy_decisions"][-1]["policy_decision_id"]

    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"target_node_id": "constitution-node", "execution_owner": "TaskRunner", "authority_source": "runtime_governance", "allowed": True},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    authority_id = session["lineage"]["governance_state_graph"]["authority"][-1]["authority_id"]

    session = manager.attach_review_required_record(
        task=task,
        state=state,
        review={"policy_decision_id": policy_id, "target_node_id": "constitution-node", "reason": "constitutional self-amendment requires review"},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    review_id = session["lineage"]["governance_state_graph"]["reviews"][-1]["review_id"]

    session = manager.attach_approval_record(
        task=task,
        state=state,
        approval={"review_id": review_id, "policy_decision_id": policy_id, "target_node_id": "constitution-node", "approver": "runtime_governance", "approved": True},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    approval_id = session["lineage"]["governance_state_graph"]["approvals"][-1]["approval_id"]

    session = manager.attach_constitutional_preservation_record(
        task=task,
        state=state,
        preservation={"constitution_node_id": "constitution-node", "policy_decision_id": policy_id, "preservation_scope": "self_amendment_guard"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    preservation_id = session["lineage"]["constitutional_preservation_graph"]["preservations"][-1]["preservation_id"]

    session = manager.attach_constitutional_mutation_proposal_record(
        task=task,
        state=state,
        proposal={"target_constitution_id": "constitution-node", "preservation_id": preservation_id, "proposal": "tighten self-amendment guard"},
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    proposal_id = session["events"][-1]["payload"]["record"]["proposal_id"]

    session = manager.attach_constitutional_mutation_approval_record(
        task=task,
        state=state,
        approval={"proposal_id": proposal_id, "authority_id": authority_id, "approval_id": approval_id, "decision": "approved"},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    mutation_approval_id = session["events"][-1]["payload"]["record"]["mutation_approval_id"]

    session = manager.attach_constitutional_self_amendment_record(
        task=task,
        state=state,
        amendment={"proposal_id": proposal_id, "mutation_approval_id": mutation_approval_id, "authority_id": authority_id, "approval_id": approval_id, "target_constitution_id": "constitution-node"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    amendment_id = session["events"][-1]["payload"]["record"]["amendment_id"]

    session = manager.attach_constitutional_policy_replacement_record(
        task=task,
        state=state,
        replacement={"amendment_id": amendment_id, "proposal_id": proposal_id, "old_policy_id": "runtime-constitution-policy", "new_policy_id": "runtime-constitution-policy-v2", "approval_id": approval_id},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    replacement_id = session["events"][-1]["payload"]["record"]["policy_replacement_id"]

    session = manager.attach_constitutional_governance_conflict_arbitration_record(
        task=task,
        state=state,
        arbitration={"branch_ids": ["constitution-main", "constitution-candidate"], "arbitration_id": "arb-self-amend", "decision": "prefer-approved-amendment"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_constitutional_amendment_rollback_record(
        task=task,
        state=state,
        rollback={"failed_amendment_id": amendment_id, "policy_replacement_id": replacement_id, "rollback_arbitration_id": "arb-self-amend", "rollback_status": "available"},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_constitutional_self_amendment_replay_record(
        task=task,
        state=state,
        replay={"amendment_ids": [amendment_id], "proposal_ids": [proposal_id], "policy_replacement_ids": [replacement_id], "replay_status": "validated"},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session

    summary = manager.continuity_summary(session)
    assert summary["ok"] is True
    assert summary["counts"]["constitutional_self_amendment_count"] == 1
    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    replay_event = [event for event in broken["events"] if event["event_type"] == "constitutional_self_amendment_replay"][-1]
    replay_event["payload"] = dict(replay_event["payload"])
    replay_event["payload"]["record"] = dict(replay_event["payload"]["record"])
    replay_event["payload"]["record"]["amendment_ids"] = ["stale-amendment"]
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "constitutional_self_amendment_replay_stale_lineage" in broken_summary["breaks"]


def test_runtime_constitutional_memory_epoch_migration_continuity() -> None:
    from core.runtime.runtime_replay_engine import build_epoch_migration_replay_validation

    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-epoch-migration", "steps": []}
    state = {"task_id": "wf-epoch-migration", "status": "running", "steps": []}

    session = manager.start_from_intent(
        intent={"task_id": "wf-epoch-migration", "goal": "migrate runtime constitution epoch"},
        task=task,
        state=state,
        current_tick=1,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_execution_graph_node_record(
        task=task,
        state=state,
        node={"node_id": "constitution-node", "label": "active constitution", "node_type": "constitution"},
        current_tick=2,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_policy_decision_record(
        task=task,
        state=state,
        decision={"target_node_id": "constitution-node", "policy_id": "runtime-constitution-policy", "allowed": True, "decision": "allow"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    policy_id = session["lineage"]["governance_state_graph"]["policy_decisions"][-1]["policy_decision_id"]

    session = manager.attach_authority_continuity_record(
        task=task,
        state=state,
        authority={"target_node_id": "constitution-node", "execution_owner": "TaskRunner", "authority_source": "runtime_governance", "allowed": True},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    authority_id = session["lineage"]["governance_state_graph"]["authority"][-1]["authority_id"]

    session = manager.attach_review_required_record(
        task=task,
        state=state,
        review={"policy_decision_id": policy_id, "target_node_id": "constitution-node", "reason": "epoch migration requires review"},
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    review_id = session["lineage"]["governance_state_graph"]["reviews"][-1]["review_id"]

    session = manager.attach_approval_record(
        task=task,
        state=state,
        approval={"review_id": review_id, "policy_decision_id": policy_id, "target_node_id": "constitution-node", "approver": "runtime_governance", "approved": True},
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    approval_id = session["lineage"]["governance_state_graph"]["approvals"][-1]["approval_id"]

    session = manager.attach_constitutional_preservation_record(
        task=task,
        state=state,
        preservation={"constitution_node_id": "constitution-node", "policy_decision_id": policy_id, "preservation_scope": "epoch_migration"},
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    preservation_id = session["lineage"]["constitutional_preservation_graph"]["preservations"][-1]["preservation_id"]

    session = manager.attach_constitutional_mutation_proposal_record(
        task=task,
        state=state,
        proposal={"target_constitution_id": "constitution-node", "preservation_id": preservation_id, "proposal": "prepare epoch migration"},
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    proposal_id = session["events"][-1]["payload"]["record"]["proposal_id"]

    session = manager.attach_constitutional_mutation_approval_record(
        task=task,
        state=state,
        approval={"proposal_id": proposal_id, "authority_id": authority_id, "approval_id": approval_id, "decision": "approved"},
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    mutation_approval_id = session["events"][-1]["payload"]["record"]["mutation_approval_id"]

    session = manager.attach_constitutional_self_amendment_record(
        task=task,
        state=state,
        amendment={"proposal_id": proposal_id, "mutation_approval_id": mutation_approval_id, "authority_id": authority_id, "approval_id": approval_id, "target_constitution_id": "constitution-node"},
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    amendment_id = session["events"][-1]["payload"]["record"]["amendment_id"]

    session = manager.attach_constitutional_policy_replacement_record(
        task=task,
        state=state,
        replacement={"amendment_id": amendment_id, "proposal_id": proposal_id, "old_policy_id": "runtime-constitution-policy", "new_policy_id": "runtime-constitution-policy-v3", "approval_id": approval_id},
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    replacement_id = session["events"][-1]["payload"]["record"]["policy_replacement_id"]

    session = manager.attach_constitutional_memory_record(
        task=task,
        state=state,
        memory={"active_constitution_id": "constitution-node", "preservation_id": preservation_id, "amendment_id": amendment_id, "memory_status": "active"},
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    memory_id = session["events"][-1]["payload"]["record"]["constitutional_memory_id"]

    session = manager.attach_constitutional_inheritance_record(
        task=task,
        state=state,
        inheritance={"constitutional_memory_id": memory_id, "parent_constitution_id": "constitution-node", "child_constitution_id": "constitution-node-v3", "amendment_id": amendment_id, "policy_replacement_id": replacement_id},
        current_tick=13,
    )
    state["workflow_runtime_session"] = session
    inheritance_id = session["events"][-1]["payload"]["record"]["constitutional_inheritance_id"]

    session = manager.attach_governance_epoch_transition_record(
        task=task,
        state=state,
        transition={"constitutional_inheritance_id": inheritance_id, "from_epoch": "epoch-1", "to_epoch": "epoch-2", "authority_id": authority_id, "approval_id": approval_id},
        current_tick=14,
    )
    state["workflow_runtime_session"] = session
    epoch_id = session["events"][-1]["payload"]["record"]["governance_epoch_transition_id"]

    session = manager.attach_constitutional_migration_record(
        task=task,
        state=state,
        migration={"governance_epoch_transition_id": epoch_id, "constitutional_inheritance_id": inheritance_id, "source_constitution_id": "constitution-node", "target_constitution_id": "constitution-node-v3"},
        current_tick=15,
    )
    state["workflow_runtime_session"] = session
    migration_id = session["events"][-1]["payload"]["record"]["constitutional_migration_id"]

    session = manager.attach_migration_validation_record(
        task=task,
        state=state,
        validation={"constitutional_migration_id": migration_id, "replay_id": "epoch-replay-1", "verification_id": "epoch-verify-1", "validation_status": "validated"},
        current_tick=16,
    )
    state["workflow_runtime_session"] = session
    validation_id = session["events"][-1]["payload"]["record"]["migration_validation_id"]

    session = manager.attach_sovereign_stabilization_record(
        task=task,
        state=state,
        stabilization={"migration_validation_id": validation_id, "survivability_id": "survivability-epoch", "stabilization_status": "stable"},
        current_tick=17,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_epoch_replay_continuity_record(
        task=task,
        state=state,
        replay={"governance_epoch_transition_id": epoch_id, "constitutional_migration_id": migration_id, "migration_validation_id": validation_id, "replay_status": "validated"},
        current_tick=18,
    )
    state["workflow_runtime_session"] = session

    summary = manager.continuity_summary(session)
    assert summary["ok"] is True
    assert summary["counts"]["constitutional_memory_count"] == 1
    assert summary["counts"]["governance_epoch_transition_count"] == 1
    replay_validation = build_epoch_migration_replay_validation(workflow_runtime_session=session)
    assert replay_validation["ok"] is True
    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    epoch_replay_event = [event for event in broken["events"] if event["event_type"] == "epoch_replay_continuity"][-1]
    epoch_replay_event["payload"] = dict(epoch_replay_event["payload"])
    epoch_replay_event["payload"]["record"] = dict(epoch_replay_event["payload"]["record"])
    epoch_replay_event["payload"]["record"]["governance_epoch_transition_id"] = "stale-epoch"
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "epoch_replay_continuity_stale_epoch" in broken_summary["breaks"]


def test_runtime_sovereign_archive_constitutional_resurrection_continuity() -> None:
    from core.runtime.runtime_replay_engine import build_sovereign_archive_replay_validation

    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-sovereign-archive", "steps": []}
    state = {"task_id": "wf-sovereign-archive", "status": "running", "steps": []}

    session = manager.start_from_intent(
        intent={"task_id": "wf-sovereign-archive", "goal": "archive and resurrect runtime constitution"},
        task=task,
        state=state,
        current_tick=1,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_constitutional_archive_record(
        task=task,
        state=state,
        archive={
            "active_constitution_id": "constitution-sovereign-v1",
            "archive_scope": "long_horizon_governance",
            "archive_status": "sealed",
        },
        current_tick=2,
    )
    state["workflow_runtime_session"] = session
    archive_id = session["events"][-1]["payload"]["record"]["constitutional_archive_id"]

    session = manager.attach_long_horizon_governance_replay_record(
        task=task,
        state=state,
        replay={
            "constitutional_archive_id": archive_id,
            "replay_status": "validated",
        },
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    horizon_replay_id = session["events"][-1]["payload"]["record"]["long_horizon_replay_id"]

    session = manager.attach_sovereign_continuity_record(
        task=task,
        state=state,
        continuity={
            "constitutional_archive_id": archive_id,
            "survivability_id": "survivability-long-horizon",
            "continuity_status": "continuous",
        },
        current_tick=4,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_constitutional_resurrection_record(
        task=task,
        state=state,
        resurrection={
            "constitutional_archive_id": archive_id,
            "catastrophic_failure_id": "catastrophic-archive-loss",
            "catastrophic_recovery_id": "catastrophic-recovery-archive-loss",
            "resurrection_status": "available",
        },
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    resurrection_id = session["events"][-1]["payload"]["record"]["constitutional_resurrection_id"]

    session = manager.attach_constitutional_resurrection_validation_record(
        task=task,
        state=state,
        validation={
            "constitutional_resurrection_id": resurrection_id,
            "long_horizon_replay_id": horizon_replay_id,
            "replay_id": "resurrection-replay-1",
            "verification_id": "resurrection-verify-1",
            "validation_status": "validated",
        },
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    validation_id = session["events"][-1]["payload"]["record"]["resurrection_validation_id"]

    session = manager.attach_constitutional_archive_replay_continuity_record(
        task=task,
        state=state,
        replay={
            "constitutional_archive_id": archive_id,
            "long_horizon_replay_id": horizon_replay_id,
            "resurrection_validation_id": validation_id,
            "replay_status": "validated",
        },
        current_tick=7,
    )
    state["workflow_runtime_session"] = session

    summary = manager.continuity_summary(session)
    assert summary["ok"] is True
    assert summary["counts"]["constitutional_archive_count"] == 1
    assert summary["counts"]["constitutional_resurrection_count"] == 1
    replay_validation = build_sovereign_archive_replay_validation(workflow_runtime_session=session)
    assert replay_validation["ok"] is True
    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    archive_replay_event = [event for event in broken["events"] if event["event_type"] == "constitutional_archive_replay_continuity"][-1]
    archive_replay_event["payload"] = dict(archive_replay_event["payload"])
    archive_replay_event["payload"]["record"] = dict(archive_replay_event["payload"]["record"])
    archive_replay_event["payload"]["record"]["constitutional_archive_id"] = "stale-archive"
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "archive_replay_continuity_stale_archive" in broken_summary["breaks"]



def test_runtime_governance_kernel_consolidation_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-kernel-consolidation", "steps": []}
    state = {"task_id": "wf-kernel-consolidation", "status": "running", "steps": []}

    session = manager.start_from_intent(
        intent={"task_id": "wf-kernel-consolidation", "goal": "consolidate runtime governance kernel continuity"},
        task=task,
        state=state,
        current_tick=1,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_plan_record(
        task=task,
        state=state,
        plan={"ok": True, "steps": [{"id": "observe", "type": "inspect"}]},
        current_tick=2,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_runtime_continuity_index_record(
        task=task,
        state=state,
        index={"index_scope": "governance_kernel_consolidation"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    continuity_index_id = session["events"][-1]["payload"]["record"]["continuity_index_id"]

    session = manager.attach_runtime_lineage_compaction_record(
        task=task,
        state=state,
        compaction={"continuity_index_id": continuity_index_id, "compaction_strategy": "stable_lineage_index"},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    lineage_compaction_id = session["events"][-1]["payload"]["record"]["lineage_compaction_id"]

    session = manager.attach_runtime_constitutional_snapshot_record(
        task=task,
        state=state,
        snapshot={
            "continuity_index_id": continuity_index_id,
            "lineage_compaction_id": lineage_compaction_id,
            "snapshot": {"kernel_boundary": "continuity_only", "execution_authority": "step_executor"},
        },
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    constitutional_snapshot_id = session["events"][-1]["payload"]["record"]["constitutional_snapshot_id"]

    session = manager.attach_runtime_replay_acceleration_index_record(
        task=task,
        state=state,
        replay_index={
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "lineage_compaction_id": lineage_compaction_id,
        },
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    replay_acceleration_index_id = session["events"][-1]["payload"]["record"]["replay_acceleration_index_id"]

    session = manager.attach_runtime_governance_archive_layer_record(
        task=task,
        state=state,
        archive_layer={
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "continuity_index_id": continuity_index_id,
            "archive_layer": "runtime_governance_kernel",
        },
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    governance_archive_layer_id = session["events"][-1]["payload"]["record"]["governance_archive_layer_id"]

    session = manager.attach_runtime_governance_kernel_consolidation_record(
        task=task,
        state=state,
        consolidation={
            "continuity_index_id": continuity_index_id,
            "lineage_compaction_id": lineage_compaction_id,
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "replay_acceleration_index_id": replay_acceleration_index_id,
            "governance_archive_layer_id": governance_archive_layer_id,
        },
        current_tick=8,
    )

    summary = manager.continuity_summary(session)
    assert summary["ok"] is True
    assert summary["counts"]["runtime_governance_kernel_consolidation_count"] == 1

    replay_validation = build_governance_kernel_consolidation_replay_validation(workflow_runtime_session=session)
    assert replay_validation["ok"] is True
    assert replay_validation["schema"] == "zero.runtime_replay.governance_kernel_consolidation_validation.v1"

    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    for event in broken["events"]:
        if event.get("event_type") == "runtime_governance_kernel_consolidation":
            event["payload"] = dict(event["payload"])
            event["payload"]["record"] = dict(event["payload"]["record"])
            event["payload"]["record"]["constitutional_snapshot_id"] = "stale-snapshot"
            break
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "kernel_consolidation_without_snapshot" in broken_summary["breaks"]



def test_runtime_governance_query_storage_lifecycle_continuity() -> None:
    manager = WorkflowRuntimeSessionManager()
    task = {"task_id": "wf-storage-lifecycle", "steps": []}
    state = {"task_id": "wf-storage-lifecycle", "status": "running", "steps": []}

    session = manager.start_from_intent(
        intent={"task_id": "wf-storage-lifecycle", "goal": "query and preserve long horizon governance continuity"},
        task=task,
        state=state,
        current_tick=1,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_plan_record(
        task=task,
        state=state,
        plan={"ok": True, "steps": [{"id": "index", "type": "inspect"}]},
        current_tick=2,
    )
    state["workflow_runtime_session"] = session

    session = manager.attach_runtime_continuity_index_record(
        task=task,
        state=state,
        index={"index_scope": "governance_storage_lifecycle"},
        current_tick=3,
    )
    state["workflow_runtime_session"] = session
    continuity_index_id = session["events"][-1]["payload"]["record"]["continuity_index_id"]

    session = manager.attach_runtime_lineage_compaction_record(
        task=task,
        state=state,
        compaction={"continuity_index_id": continuity_index_id, "compaction_strategy": "queryable_replay_window"},
        current_tick=4,
    )
    state["workflow_runtime_session"] = session
    lineage_compaction_id = session["events"][-1]["payload"]["record"]["lineage_compaction_id"]

    session = manager.attach_runtime_constitutional_snapshot_record(
        task=task,
        state=state,
        snapshot={
            "continuity_index_id": continuity_index_id,
            "lineage_compaction_id": lineage_compaction_id,
            "snapshot": {"kernel_boundary": "continuity_only", "archive": "queryable"},
        },
        current_tick=5,
    )
    state["workflow_runtime_session"] = session
    constitutional_snapshot_id = session["events"][-1]["payload"]["record"]["constitutional_snapshot_id"]

    session = manager.attach_runtime_replay_acceleration_index_record(
        task=task,
        state=state,
        replay_index={
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "lineage_compaction_id": lineage_compaction_id,
        },
        current_tick=6,
    )
    state["workflow_runtime_session"] = session
    replay_acceleration_index_id = session["events"][-1]["payload"]["record"]["replay_acceleration_index_id"]

    session = manager.attach_runtime_governance_archive_layer_record(
        task=task,
        state=state,
        archive_layer={
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "continuity_index_id": continuity_index_id,
            "archive_layer": "runtime_governance_kernel",
        },
        current_tick=7,
    )
    state["workflow_runtime_session"] = session
    governance_archive_layer_id = session["events"][-1]["payload"]["record"]["governance_archive_layer_id"]

    session = manager.attach_runtime_governance_kernel_consolidation_record(
        task=task,
        state=state,
        consolidation={
            "continuity_index_id": continuity_index_id,
            "lineage_compaction_id": lineage_compaction_id,
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "replay_acceleration_index_id": replay_acceleration_index_id,
            "governance_archive_layer_id": governance_archive_layer_id,
        },
        current_tick=8,
    )
    state["workflow_runtime_session"] = session
    kernel_consolidation_id = session["events"][-1]["payload"]["record"]["kernel_consolidation_id"]

    session = manager.attach_runtime_governance_query_index_record(
        task=task,
        state=state,
        query_index={
            "continuity_index_id": continuity_index_id,
            "kernel_consolidation_id": kernel_consolidation_id,
            "query_keys": ["workflow_id", "session_id", "event_type", "lineage_ref"],
        },
        current_tick=9,
    )
    state["workflow_runtime_session"] = session
    governance_query_index_id = session["events"][-1]["payload"]["record"]["governance_query_index_id"]

    session = manager.attach_runtime_replay_window_record(
        task=task,
        state=state,
        replay_window={
            "replay_acceleration_index_id": replay_acceleration_index_id,
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "start_tick": 1,
            "end_tick": 9,
        },
        current_tick=10,
    )
    state["workflow_runtime_session"] = session
    replay_window_id = session["events"][-1]["payload"]["record"]["replay_window_id"]

    session = manager.attach_runtime_lineage_pruning_record(
        task=task,
        state=state,
        pruning={
            "lineage_compaction_id": lineage_compaction_id,
            "continuity_index_id": continuity_index_id,
            "pruning_strategy": "retain_queryable_constitutional_window",
        },
        current_tick=11,
    )
    state["workflow_runtime_session"] = session
    lineage_pruning_id = session["events"][-1]["payload"]["record"]["lineage_pruning_id"]

    session = manager.attach_runtime_sovereign_archive_reconstruction_record(
        task=task,
        state=state,
        reconstruction={
            "governance_archive_layer_id": governance_archive_layer_id,
            "constitutional_snapshot_id": constitutional_snapshot_id,
            "governance_query_index_id": governance_query_index_id,
        },
        current_tick=12,
    )
    state["workflow_runtime_session"] = session
    sovereign_archive_reconstruction_id = session["events"][-1]["payload"]["record"]["sovereign_archive_reconstruction_id"]

    session = manager.attach_runtime_continuity_storage_lifecycle_record(
        task=task,
        state=state,
        lifecycle={
            "governance_query_index_id": governance_query_index_id,
            "replay_window_id": replay_window_id,
            "lineage_pruning_id": lineage_pruning_id,
            "sovereign_archive_reconstruction_id": sovereign_archive_reconstruction_id,
            "kernel_consolidation_id": kernel_consolidation_id,
        },
        current_tick=13,
    )

    summary = manager.continuity_summary(session)
    assert summary["ok"] is True
    assert summary["counts"]["runtime_continuity_storage_lifecycle_count"] == 1

    replay_validation = build_governance_storage_lifecycle_replay_validation(workflow_runtime_session=session)
    assert replay_validation["ok"] is True
    assert replay_validation["schema"] == "zero.runtime_replay.governance_storage_lifecycle_validation.v1"

    json.dumps(session, sort_keys=True, default=str)

    broken = dict(session)
    broken["events"] = [dict(event) for event in session["events"]]
    for event in broken["events"]:
        if event.get("event_type") == "runtime_continuity_storage_lifecycle":
            event["payload"] = dict(event["payload"])
            event["payload"]["record"] = dict(event["payload"]["record"])
            event["payload"]["record"]["sovereign_archive_reconstruction_id"] = "stale-reconstruction"
            break
    broken_summary = manager.continuity_summary(broken)
    assert broken_summary["ok"] is False
    assert "storage_lifecycle_without_archive_reconstruction" in broken_summary["breaks"]
