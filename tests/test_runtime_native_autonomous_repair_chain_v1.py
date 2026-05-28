from __future__ import annotations

from core.runtime.runtime_native_autonomous_repair_chain import (
    FAILURE_CLASS_CONTENT,
    REPAIR_STATUS_FINALIZED,
    REPAIR_STATUS_RETRY_LIMIT_REACHED,
    RuntimeNativeAutonomousRepairChain,
)
from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_targeted_pytest_planner import RuntimeNativeTargetedPytestPlanner


def test_autonomous_repair_chain_repairs_failed_content(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    pytest_planner = RuntimeNativeTargetedPytestPlanner.with_workspace(tmp_path)
    chain = RuntimeNativeAutonomousRepairChain.with_workspace(
        tmp_path,
        mutation_loop=mutation,
        pytest_planner=pytest_planner,
    )

    result = chain.run_repair_chain(
        goal="repair content",
        initial_plan_fn=lambda goal, context: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "VALUE = 'broken'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": target.read_text(encoding="utf-8") == "VALUE = 'fixed'\n",
            "command": "content verify",
            "stderr": "content mismatch",
        },
        repair_plan_fn=lambda record, attempt: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "VALUE = 'fixed'\n",
                }
            ],
        },
        max_retries=1,
    )

    assert result.status == REPAIR_STATUS_FINALIZED
    assert result.final_result["ok"] is True
    assert len(result.attempts) == 2
    assert result.attempts[0].failure_class == FAILURE_CLASS_CONTENT
    assert target.read_text(encoding="utf-8") == "VALUE = 'fixed'\n"


def test_autonomous_repair_chain_retry_limit(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    chain = RuntimeNativeAutonomousRepairChain.with_workspace(
        tmp_path,
        mutation_loop=mutation,
    )

    result = chain.run_repair_chain(
        goal="cannot repair",
        initial_plan_fn=lambda goal, context: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "VALUE = 'broken'\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": False,
            "command": "pytest targeted",
            "stderr": "assert failed",
        },
        repair_plan_fn=lambda record, attempt: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "VALUE = 'still broken'\n",
                }
            ],
        },
        max_retries=1,
    )

    assert result.status == REPAIR_STATUS_RETRY_LIMIT_REACHED
    assert result.final_result["ok"] is False
    assert len(result.attempts) == 2


def test_autonomous_repair_chain_persists(tmp_path):
    mutation = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    chain = RuntimeNativeAutonomousRepairChain.with_workspace(tmp_path, mutation_loop=mutation)

    record = chain.create_chain(goal="persist repair chain")

    reloaded = RuntimeNativeAutonomousRepairChain.with_workspace(tmp_path, mutation_loop=mutation)

    assert reloaded.get_chain(record.repair_chain_id).repair_chain_id == record.repair_chain_id
