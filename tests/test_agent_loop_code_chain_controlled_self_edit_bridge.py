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


class PlannerOwnedRoutePlanner(CodeFixPlanner):
    def plan(self, context=None, user_input="", route=None, **kwargs):
        result = super().plan(context=context, user_input=user_input, route=route, **kwargs)
        result.update(
            {
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
        )
        return result


class GenericPlanner:
    def __init__(self) -> None:
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        return {
            "ok": True,
            "goal": "Summarize notes",
            "steps": [{"type": "respond", "message": "summary ready"}],
            "execution_route": "generic_planner_path",
            "semantic_type": "generic_task",
        }


def test_agent_loop_code_fix_without_dispatcher_capability_is_blocked(tmp_path: Path) -> None:
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

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["code_chain_controlled_self_edit_bridge"] is True
    assert result["controlled_mutation_plan_produced"] is True
    assert len(planner.calls) == 1

    plan = result["plan"]
    assert plan["controlled_mutation_plan"][0]["type"] == "apply_patch"
    assert plan["boundary"]["step_executor_executes"] is False
    assert plan["boundary"]["runtime_dispatcher_required"] is True
    assert plan["boundary"]["runtime_file_service_required"] is True
    assert plan["boundary"]["runtime_mutation_gateway_required"] is True

    execution = result["execution"]
    assert execution["ok"] is False
    assert execution["executed"] is False
    assert execution["blocked"] is True
    assert execution["status"] != "completed"
    assert execution["error"]

    review = result["reviewable_result"]
    assert review["ok"] is False
    assert review["status"] != "ok"
    assert review["task_id"]
    assert review["changed_files"] == []
    assert review["failure_reason"]

    assert target.read_text(encoding="utf-8") == "def status():\n    return 'broken'\n"


def test_agent_loop_planner_owned_code_chain_without_dispatcher_lineage_is_blocked(tmp_path: Path) -> None:
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target = workspace_root / "shared" / "planner_owned.py"
    target.parent.mkdir(parents=True)
    target.write_text("def status():\n    return 'broken'\n", encoding="utf-8")

    planner = PlannerOwnedRoutePlanner("workspace/shared/planner_owned.py", repo_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=StepExecutor(workspace_root=workspace_root),
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("please handle ticket 123")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"
    assert result["planner_owned_intent_routing"] is True
    assert result["code_chain_v1_fallback_used"] is False
    assert result["plan"]["route_decision"]["source"] == "planner_route_metadata"
    assert result["plan"]["route_decision"]["task_kind"] == "code_fix"
    assert result["execution"]["error"]
    assert result["reviewable_result"]["changed_files"] == []
    assert target.read_text(encoding="utf-8") == "def status():\n    return 'broken'\n"


def test_agent_loop_non_code_planner_route_does_not_enter_code_chain(tmp_path: Path) -> None:
    planner = GenericPlanner()
    loop = AgentLoop(
        planner=planner,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("summarize quarterly planning notes")

    assert result.get("mode") != "code_chain_controlled_self_edit_bridge"
    assert result.get("code_chain_controlled_self_edit_bridge") is not True
    assert result.get("planner_owned_intent_routing") is not True
