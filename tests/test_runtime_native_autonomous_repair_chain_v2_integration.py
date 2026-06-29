
from pathlib import Path

from core.runtime.runtime_native_autonomous_repair_chain import RuntimeNativeAutonomousRepairChain
from core.runtime.step_executor import StepExecutor
import pytest

pytestmark = [pytest.mark.integration]




class FakeMutationRecord:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


class FakeMutationLoop:
    def __init__(self):
        self.calls = 0

    def run_mutation(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return FakeMutationRecord(
                {
                    "mutation_id": "m1",
                    "status": "failed_verification",
                    "verifications": [{"ok": False, "stderr": "pytest failed"}],
                    "final_result": {"ok": False},
                }
            )
        return FakeMutationRecord(
            {
                "mutation_id": "m2",
                "status": "finalized",
                "verifications": [{"ok": True, "stdout": "1 passed"}],
                "final_result": {"ok": True},
            }
        )


def test_runtime_chain_v2_finalizes_after_repair(tmp_path: Path):
    chain = RuntimeNativeAutonomousRepairChain(workspace_root=tmp_path, mutation_loop=FakeMutationLoop())
    record = chain.run_repair_chain(
        goal="fix failing test",
        initial_plan_fn=lambda goal, context: {"goal": goal},
        verify_fn=lambda mutation: {"ok": True},
        repair_plan_fn=lambda record, attempt: {"goal": "repair", "failure_class": attempt.failure_class},
        max_retries=1,
    )
    envelope = chain.to_runtime_execution_result(record)
    assert envelope["ok"] is True
    assert envelope["status"] == "finalized"
    assert envelope["attempt_count"] == 2
    assert envelope["audit_trace"][-1]["type"] == "autonomous_repair_finalize"


def test_step_executor_autonomous_repair_chain_handler(tmp_path: Path):
    executor = StepExecutor(workspace_root=str(tmp_path))
    result = executor.execute_step(
        {
            "type": "autonomous_repair_chain",
            "goal": "fix failing test through runtime",
            "mutation_loop": FakeMutationLoop(),
            "max_retries": 1,
            "repair_plan": {"goal": "repair"},
        },
        task={"task_id": "task-autorepair"},
        context={},
    )
    assert result["ok"] is True
    assert result["step_type"] == "autonomous_repair_chain"
    assert result["result"]["runtime_phase"] == "autonomous_repair_chaining_v2"
    assert result["result"]["result"]["status"] == "finalized"
