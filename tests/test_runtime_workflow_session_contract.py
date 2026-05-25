from __future__ import annotations

import json

from core.runtime.workflow_runtime_session import WorkflowRuntimeSessionManager, build_workflow_runtime_session
from core.runtime.runtime_replay_engine import build_replayable_workflow_runtime_session
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
