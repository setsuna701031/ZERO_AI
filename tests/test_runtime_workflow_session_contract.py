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
