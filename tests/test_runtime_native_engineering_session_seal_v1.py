from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_engineering_session import RuntimeNativeEngineeringSession
from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_multisession_coordination import RuntimeNativeMultiSessionCoordination
from core.runtime.runtime_native_repo_engineering_surface import RuntimeNativeRepoEngineeringSurface
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def test_runtime_native_engineering_session_seal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "core/runtime/runtime_native_engineering_target.py").write_text(
        "VALUE = 'broken'\n",
        encoding="utf-8",
    )

    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "engineering-session-runtime",
            "namespace": "zero.engineering.session",
            "owner_id": "engineering-owner",
            "source_session_id": "engineering-session",
            "allowed_paths": ["aer://task/", "workspace/", "runtime-signal://"],
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(tmp_path / "scheduler", mainline=mainline)
    dispatch = RuntimeNativeExecutionDispatch.with_workspace(tmp_path / "dispatch", mainline=mainline, scheduler=scheduler)
    coordination = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
    )

    repo_surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)
    mutation_loop = RuntimeNativeCodeMutationLoop.with_workspace(
        tmp_path,
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
        recovery_orchestrator=mainline.orchestrator,
    )
    session = RuntimeNativeEngineeringSession.with_workspace(
        tmp_path,
        repo_surface=repo_surface,
        mutation_loop=mutation_loop,
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
        coordination=coordination,
    )

    opened = session.open_session(goal="fix engineering target runtime file")
    captured = session.capture_repo_context(opened.session_id, keywords=["engineering", "target", "runtime"])

    assert captured.status == "running"
    assert len(captured.engineering_task["impacted_files"]) >= 1

    failed_once = {"value": False}

    def verify(record):
        ok = (tmp_path / "core/runtime/runtime_native_engineering_target.py").read_text(encoding="utf-8") == "VALUE = 'fixed'\n"
        if not failed_once["value"]:
            failed_once["value"] = True
            ok = False
        return {
            "ok": ok,
            "command": "targeted verification",
        }

    completed = session.run_mutation(
        captured.session_id,
        plan_fn=lambda goal, context: {
            "impacted_files": ["core/runtime/runtime_native_engineering_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_engineering_target.py",
                    "content": "VALUE = 'broken'\n",
                }
            ],
        },
        verify_fn=verify,
        repair_fn=lambda record, failure: {
            "impacted_files": ["core/runtime/runtime_native_engineering_target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_engineering_target.py",
                    "content": "VALUE = 'fixed'\n",
                }
            ],
        },
        max_retries=1,
    )

    assert completed.status == "completed"
    assert completed.final_result["ok"] is True
    assert completed.mutation_history[0]["retry_count"] == 1
    assert len(completed.verification_history) == 2
    assert len(completed.timeline) >= 5

    node_a = coordination.register_node(
        runtime_id="engineering-planner",
        namespace="zero.engineering.planner",
        owner_id="planner-owner",
        source_session_id="planner-session",
    )
    node_b = coordination.register_node(
        runtime_id="engineering-session-runtime",
        namespace="zero.engineering.executor",
        owner_id="engineering-owner",
        source_session_id="engineering-session",
    )

    dispatched = coordination.dispatch_between_nodes(
        source_node_id=node_a.node_id,
        target_node_id=node_b.node_id,
        goal="engineering session followup",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "followup"}]},
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert dispatched["ok"] is True
    assert dispatched["dispatch"]["status"] == "completed"

    health = session.health()
    assert health["counts"]["completed"] == 1
