from __future__ import annotations

import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor


class WorkcopyCodeFixPlanner:
    def __init__(self, *, target_path: str, repo_root: Path) -> None:
        self.target_path = target_path
        self.repo_root = repo_root
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        return {
            "ok": True,
            "goal": "Fix workcopy status function",
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
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "change workcopy status from failing to passing",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": 'return "failing"',
                        "new_text": 'return "passing"',
                    },
                    "verify_contains": 'return "passing"',
                    "verify_not_contains": 'return "failing"',
                    "verify_python_syntax": True,
                },
                {
                    "type": "command",
                    "description": "compile workcopy file",
                    "command": f'"{sys.executable}" -m py_compile {self.target_path}',
                    "command_cwd": str(self.repo_root),
                },
            ],
        }


def test_agent_loop_code_chain_real_workcopy_governed_edit(tmp_path: Path) -> None:
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target_path = "workspace/shared/workcopy/real_failure.py"
    target = repo_root / target_path
    untouched = workspace_root / "shared" / "workcopy" / "untouched.py"
    target.parent.mkdir(parents=True)
    target.write_text('def status():\n    return "failing"\n', encoding="utf-8")
    untouched.write_text('def status():\n    return "untouched"\n', encoding="utf-8")

    planner = WorkcopyCodeFixPlanner(target_path=target_path, repo_root=repo_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=StepExecutor(workspace_root=workspace_root),
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("fix the failing workcopy code using the planner-owned Code Chain route")

    assert result["ok"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["code_chain_controlled_self_edit_bridge"] is True
    assert result["planner_owned_intent_routing"] is True
    assert result["code_chain_v1_fallback_used"] is False
    assert len(planner.calls) == 1

    plan = result["plan"]
    assert plan["route_decision"]["source"] == "planner_route_metadata"
    assert plan["route_decision"]["route"] == "code_chain_controlled_self_edit"
    assert plan["route_decision"]["task_kind"] == "code_fix"
    assert plan["route_decision"]["requires_controlled_mutation"] is True
    assert plan["controlled_mutation_plan"][0]["type"] == "controlled_edit"
    assert plan["steps"][0]["type"] == "apply_patch"

    execution = result["execution"]
    edit_step_result = execution["results"][0]["result"]
    command_result = execution["results"][1]["result"]["result"]
    assert edit_step_result["transaction_ok"] is True
    assert edit_step_result["verification_ok"] is True
    assert edit_step_result["runtime_transaction_id"]
    assert edit_step_result["runtime_transaction"]["surface"] == "apply_patch"
    assert target_path in edit_step_result["runtime_transaction"]["affected_files"]
    assert edit_step_result["canonical_evidence"]["evidence_refs"]
    assert command_result["returncode"] == 0

    assert target.read_text(encoding="utf-8") == 'def status():\n    return "passing"\n'
    assert untouched.read_text(encoding="utf-8") == 'def status():\n    return "untouched"\n'

    review = result["reviewable_result"]
    assert review["ok"] is True
    assert review["status"] == "ok"
    assert target_path in review["changed_files"]
    assert review["changed_file_reasons"] == [
        {
            "path": target_path,
            "reason": "change workcopy status from failing to passing",
        }
    ]
    assert "py_compile" in review["verification_command"]
    assert "returncode=0" in review["verification_output_summary"]
    assert "review_required" in review
    assert review["review_required"] is False
    assert review["human_review_required"] is False
    assert review["failure_reason"] == ""
