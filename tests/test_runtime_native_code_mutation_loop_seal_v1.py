from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_multisession_coordination import RuntimeNativeMultiSessionCoordination
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def test_runtime_native_code_mutation_loop_seal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "mutation-seal-runtime",
            "namespace": "zero.mutation.seal",
            "owner_id": "mutation-owner",
            "source_session_id": "mutation-session",
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
    mutation = RuntimeNativeCodeMutationLoop.with_workspace(
        tmp_path,
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
        recovery_orchestrator=mainline.orchestrator,
    )

    result = mutation.run_mutation(
        goal="codex-like mutation seal",
        plan_fn=lambda goal, context: {
            "impacted_files": ["src/app.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "src/app.py",
                    "content": "broken",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": (tmp_path / "src/app.py").read_text(encoding="utf-8") == "fixed",
            "command": "python -m pytest targeted",
            "stdout": "targeted verification",
        },
        repair_fn=lambda record, failure: {
            "impacted_files": ["src/app.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "src/app.py",
                    "content": "fixed",
                }
            ],
        },
        max_retries=1,
    )

    assert result.status == "finalized"
    assert result.final_result["ok"] is True
    assert result.retry_count == 1
    assert len(result.verifications) == 2
    assert (tmp_path / "src/app.py").read_text(encoding="utf-8") == "fixed"
    assert mutation.health()["counts"]["finalized"] == 1

    node_a = coordination.register_node(
        runtime_id="mutation-planner",
        namespace="zero.mutation.planner",
        owner_id="planner-owner",
        source_session_id="planner-session",
    )
    node_b = coordination.register_node(
        runtime_id="mutation-seal-runtime",
        namespace="zero.mutation.execution",
        owner_id="mutation-owner",
        source_session_id="mutation-session",
    )

    dispatched = coordination.dispatch_between_nodes(
        source_node_id=node_a.node_id,
        target_node_id=node_b.node_id,
        goal="mutation loop followup dispatch",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "followup"}]},
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert dispatched["ok"] is True
    assert dispatched["dispatch"]["status"] == "completed"
