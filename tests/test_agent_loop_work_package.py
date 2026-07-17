from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop


def _write_target(repo_root: Path) -> None:
    target = repo_root / "core/agent/agent_component_invoker.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def invoke():\n"
        "    previous_result = None\n"
        "    return previous_result\n",
        encoding="utf-8",
    )


def test_agent_loop_dispatches_work_package_explore_mode(tmp_path: Path) -> None:
    _write_target(tmp_path)
    before = (tmp_path / "core/agent/agent_component_invoker.py").read_text(encoding="utf-8")

    loop = AgentLoop()
    response = loop.run(
        json.dumps(
            {
                "task_type": "work_package",
                "repo_root": str(tmp_path),
                "package_id": "agent_loop_legacy_audit",
                "kind": "readonly_audit",
                "mode": "explore",
                "title": "AgentLoop legacy audit",
                "scope_paths": ["core/agent/agent_component_invoker.py"],
                "report_path": "workspace/agent_loop_legacy_audit.md",
            }
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "work_package"
    assert response["agent_loop_runtime_route"] == "controlled_work_package_intake"
    assert response["work_package_mode"] == "explore"
    assert response["report_path"] == "workspace/agent_loop_legacy_audit.md"
    assert response["work_package_result"]["mutation_allowed"] is False
    assert (tmp_path / "workspace/agent_loop_legacy_audit.md").exists()
    assert (tmp_path / response["result_path"]).exists()
    assert (tmp_path / "core/agent/agent_component_invoker.py").read_text(encoding="utf-8") == before


def test_agent_loop_dispatches_work_package_plan_mode(tmp_path: Path) -> None:
    _write_target(tmp_path)

    loop = AgentLoop()
    response = loop.run(
        json.dumps(
            {
                "task_type": "work_package",
                "repo_root": str(tmp_path),
                "package_id": "agent_loop_plan",
                "kind": "readonly_audit",
                "mode": "plan",
                "title": "Plan legacy cleanup",
                "scope_paths": ["core/agent/agent_component_invoker.py"],
                "report_path": "workspace/agent_loop_plan.md",
            }
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "work_package"
    assert response["work_package_mode"] == "plan"
    assert response["work_package_result"]["plan"]["reason"] == "plan_mode_readonly"
    assert (tmp_path / "workspace/agent_loop_plan.md").exists()


def test_agent_loop_execute_work_package_requires_approval(tmp_path: Path) -> None:
    _write_target(tmp_path)
    before = (tmp_path / "core/agent/agent_component_invoker.py").read_text(encoding="utf-8")

    loop = AgentLoop()
    response = loop.run(
        json.dumps(
            {
                "task_type": "work_package",
                "repo_root": str(tmp_path),
                "package_id": "agent_loop_execute",
                "kind": "readonly_audit",
                "mode": "execute",
                "title": "Execute legacy cleanup",
                "scope_paths": ["core/agent/agent_component_invoker.py"],
                "report_path": "workspace/agent_loop_execute.md",
                "approval": False,
            }
        )
    )

    assert response["ok"] is False
    assert response["mode"] == "work_package"
    assert response["work_package_mode"] == "execute"
    assert response["work_package_result"]["blocked"] is True
    assert response["work_package_result"]["approval_required"] is True
    assert response["work_package_result"]["mutation_allowed"] is False
    assert (tmp_path / "core/agent/agent_component_invoker.py").read_text(encoding="utf-8") == before


def test_agent_loop_ignores_non_json_normal_text() -> None:
    loop = AgentLoop(router={"mode": "direct"})
    response = loop.run("hello")
    assert response["mode"] != "work_package"
