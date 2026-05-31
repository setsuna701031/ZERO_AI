from __future__ import annotations

import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor


class CodeFixPlanner:
    def __init__(self, target_path: str, command_cwd: Path) -> None:
        self.target_path = target_path
        self.command_cwd = command_cwd
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        return {
            "ok": True,
            "goal": "Fix sandbox code failure through controlled mutation",
            "steps": [
                {
                    "type": "apply_patch",
                    "description": "replace failing return value with passing value",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": "return 'broken'",
                        "new_text": "return 'fixed'",
                    },
                    "verify_contains": "return 'fixed'",
                    "verify_not_contains": "return 'broken'",
                    "verify_python_syntax": True,
                },
                {
                    "type": "command",
                    "description": "compile changed sandbox file",
                    "command": f'"{sys.executable}" -m py_compile {self.target_path}',
                    "command_cwd": str(self.command_cwd),
                },
            ],
            "execution_route": "code_chain_controlled_self_edit_bridge",
            "semantic_type": "code_fix_controlled_edit",
        }


def test_agent_loop_code_fix_routes_to_governed_controlled_mutation(tmp_path: Path) -> None:
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target = workspace_root / "shared" / "sandbox_failure.py"
    target.parent.mkdir(parents=True)
    target.write_text("def status():\n    return 'broken'\n", encoding="utf-8")

    planner = CodeFixPlanner("workspace/shared/sandbox_failure.py", repo_root)
    step_executor = StepExecutor(workspace_root=workspace_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("fix a code failure in a sandbox/workcopy file")

    assert result["ok"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["code_chain_controlled_self_edit_bridge"] is True
    assert result["controlled_mutation_plan_produced"] is True
    assert len(planner.calls) == 1

    plan = result["plan"]
    assert plan["controlled_mutation_plan"][0]["type"] == "apply_patch"
    assert plan["boundary"]["step_executor_executes"] is True
    assert plan["boundary"]["runtime_file_service_required"] is True
    assert plan["boundary"]["runtime_mutation_gateway_required"] is True

    execution = result["execution"]
    assert execution["ok"] is True
    assert execution["results"][0]["step"]["type"] == "apply_patch"
    assert execution["results"][0]["result"]["transaction_ok"] is True
    assert execution["results"][0]["result"]["verification_ok"] is True
    assert execution["results"][1]["step"]["type"] == "command"
    assert execution["results"][1]["result"]["result"]["returncode"] == 0

    review = result["reviewable_result"]
    assert review["ok"] is True
    assert review["status"] == "ok"
    assert review["task_id"]
    assert "workspace/shared/sandbox_failure.py" in review["changed_files"]
    assert review["changed_file_reasons"] == [
        {
            "path": "workspace/shared/sandbox_failure.py",
            "reason": "replace failing return value with passing value",
        }
    ]
    assert "py_compile" in review["verification_command"]
    assert "returncode=0" in review["verification_output_summary"]
    assert review["human_review_required"] is False
    assert review["failure_reason"] == ""

    assert target.read_text(encoding="utf-8") == "def status():\n    return 'fixed'\n"
