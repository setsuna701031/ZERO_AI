from __future__ import annotations

import inspect
import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.agent.code_chain_repair_report import normalize_code_chain_repair_report
from core.runtime.step_executor import StepExecutor


class RepairPropagationPlanner:
    def __init__(self, *, target_path: str, repo_root: Path) -> None:
        self.target_path = target_path
        self.repo_root = repo_root
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        context = context if isinstance(context, dict) else {}
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        if context.get("repair_loop"):
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
            "goal": "Initial edit fails verification for report propagation",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "first attempt leaves verifier unsatisfied",
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
            "goal": "Repair edit fixes verification for report propagation",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "repair attempt satisfies verifier",
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


def test_blocked_code_chain_does_not_propagate_successful_repair_history(tmp_path: Path) -> None:
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target_path = "workspace/shared/workcopy/repair_report_target.py"
    target = repo_root / target_path
    target.parent.mkdir(parents=True)
    target.write_text('def status():\n    return "broken"\n', encoding="utf-8")

    planner = RepairPropagationPlanner(target_path=target_path, repo_root=repo_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=StepExecutor(workspace_root=workspace_root),
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("fix the workcopy failure and report autonomous repair attempts")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["execution"]["executed"] is False
    assert result["execution"]["error"]
    assert len(planner.calls) == 1
    assert target.read_text(encoding="utf-8") == 'def status():\n    return "broken"\n'
    assert "repair_result_report" not in result
    assert result.get("finished") is not True
    assert result.get("completed") is not True


def test_repair_report_helper_normalizes_existing_fields_without_agentloop_ownership() -> None:
    report = normalize_code_chain_repair_report(
        ok=True,
        execution={
            "original_failure": {"ok": False, "message": "verify_contains failed"},
            "attempt_history": [
                {"attempt_index": 1, "attempt_kind": "initial", "ok": False},
                {"attempt_index": 2, "attempt_kind": "repair", "ok": True},
            ],
            "verification_history": [
                {"attempt_index": 1, "ok": False},
                {"attempt_index": 2, "ok": True},
            ],
        },
        reviewable_result={
            "status": "ok",
            "attempt_count": 2,
            "failure_reason": "verify_contains failed",
            "final_result": "passed",
        },
    )

    assert report["ok"] is True
    assert report["first_attempt_failed"] is True
    assert report["repair_attempt_executed"] is True
    assert report["verification_passed"] is True
    assert report["failure_reason"] == "verify_contains failed"

    agent_loop_source = inspect.getsource(AgentLoop)
    assert "code_chain_repair_report" not in agent_loop_source
    assert "repair_result_report" not in agent_loop_source
