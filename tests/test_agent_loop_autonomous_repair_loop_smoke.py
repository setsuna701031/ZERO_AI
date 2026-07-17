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

    assert result["ok"] is False
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["planner_owned_intent_routing"] is True
    assert target.read_text(encoding="utf-8") == 'def status():\n    return "broken"\n'
