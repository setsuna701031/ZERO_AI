from __future__ import annotations

import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor


class RepairLoopPlanner:
    def __init__(self, *, target_path: str, repo_root: Path) -> None:
        self.target_path = target_path
        self.repo_root = repo_root
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        context = context if isinstance(context, dict) else {}
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        if context.get("repair_loop"):
            assert context.get("previous_failure")
            return self._repair_plan()
        return self._failing_plan()

    def _route_metadata(self) -> dict:
        return {
            "code_chain_intent": True,
            "route": "code_chain_controlled_self_edit",
            "task_kind": "code_fix",
            "requires_controlled_mutation": True,
            "route_metadata": {
                "code_chain_intent": True,
                "route": "code_chain_controlled_self_edit",
                "task_kind": "code_fix",
                "requires_controlled_mutation": True,
            },
        }

    def _failing_plan(self) -> dict:
        return {
            "ok": True,
            "goal": "Initial controlled edit with intentionally wrong verification",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "first attempt changes status to almost fixed",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": 'return "broken"',
                        "new_text": 'return "almost_fixed"',
                    },
                    "verify_contains": 'return "fixed"',
                    "verify_not_contains": 'return "broken"',
                    "verify_python_syntax": True,
                }
            ],
        }

    def _repair_plan(self) -> dict:
        return {
            "ok": True,
            "goal": "Repair controlled edit after verification failure",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "repair attempt changes status to fixed",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": 'return "broken"',
                        "new_text": 'return "fixed"',
                    },
                    "verify_contains": 'return "fixed"',
                    "verify_not_contains": 'return "broken"',
                    "verify_python_syntax": True,
                },
                {
                    "type": "command",
                    "description": "compile repaired workcopy file",
                    "command": f'"{sys.executable}" -m py_compile {self.target_path}',
                    "command_cwd": str(self.repo_root),
                },
            ],
        }


def test_agent_loop_autonomous_repair_loop_after_verification_failure(tmp_path: Path) -> None:
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target_path = "workspace/shared/workcopy/repair_loop_target.py"
    target = repo_root / target_path
    target.parent.mkdir(parents=True)
    target.write_text('def status():\n    return "broken"\n', encoding="utf-8")

    planner = RepairLoopPlanner(target_path=target_path, repo_root=repo_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=StepExecutor(workspace_root=workspace_root),
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("fix the broken workcopy code through planner-owned Code Chain")

    assert result["ok"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["planner_owned_intent_routing"] is True
    assert result["repair_loop_entered"] is True
    assert len(planner.calls) == 2
    assert planner.calls[1]["context"]["repair_loop"] is True
    assert planner.calls[1]["context"]["previous_failure"]["ok"] is False

    execution = result["execution"]
    assert execution["repair_loop_entered"] is True
    assert execution["original_failure"]["ok"] is False
    assert "verify_contains failed" in execution["original_failure"]["message"]

    attempt_history = execution["attempt_history"]
    assert [attempt["attempt_kind"] for attempt in attempt_history] == ["initial", "repair"]
    assert attempt_history[0]["ok"] is False
    assert "verify_contains failed" in attempt_history[0]["failure_reason"]
    assert attempt_history[1]["ok"] is True

    repaired_step_result = execution["results"][0]["result"]
    assert repaired_step_result["transaction_ok"] is True
    assert repaired_step_result["verification_ok"] is True
    assert repaired_step_result["runtime_transaction_id"]
    assert repaired_step_result["runtime_transaction"]["surface"] == "apply_patch"
    assert target_path in repaired_step_result["runtime_transaction"]["affected_files"]
    assert repaired_step_result["canonical_evidence"]["evidence_refs"]

    assert target.read_text(encoding="utf-8") == 'def status():\n    return "fixed"\n'

    review = result["reviewable_result"]
    assert review["status"] == "ok"
    assert review["attempt_count"] == 2
    assert target_path in review["changed_files"]
    assert len(review["verification_history"]) == 2
    assert review["verification_history"][0]["ok"] is False
    assert "verify_contains failed" in review["verification_history"][0]["failure_reason"]
    assert review["verification_history"][1]["ok"] is True
    assert "py_compile" in review["verification_history"][1]["verification_command"]
    assert "verify_contains failed" in review["failure_reason"]
    assert review["repair_reason"].startswith("verification failed")
    assert review["final_result"] == "passed"
    assert review["review_required"] is False
