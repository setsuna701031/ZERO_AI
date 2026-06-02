from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.planning.planner import Planner


def _aer_task_payload(
    *,
    repo_root: Path,
    package_id: str,
    target_path: str,
    content: str,
    approval: bool = True,
) -> str:
    return json.dumps(
        {
            "task_type": "aer_task",
            "repo_root": str(repo_root),
            "task_id": package_id,
            "goal": f"write {target_path}",
            "operation": "write_file",
            "target_path": target_path,
            "content": content,
            "approval": approval,
        }
    )


def test_aer_task_converts_to_work_package_and_runs_controlled_chain(tmp_path: Path) -> None:
    loop = AgentLoop(planner=Planner(), repo_root=str(tmp_path))

    response = loop.run(
        _aer_task_payload(
            repo_root=tmp_path,
            package_id="aer_closure_ok",
            target_path="workspace/aer_closure.txt",
            content="AER closure result\n",
            approval=True,
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "work_package"
    assert response["agent_loop_runtime_route"] == "work_package_scheduler"
    assert response["package_id"] == "aer_closure_ok"
    assert response["execution_mode"] == "execute"

    plan = response["plan"]
    intent = plan["normalized_execution_intent"]
    assert intent["schema"] == "zero.aer.normalized_execution_intent.v1"
    assert intent["work_package"]["package_id"] == "aer_closure_ok"
    assert intent["work_package"]["edit"]["target_path"] == "workspace/aer_closure.txt"

    result = response["work_package_result"]
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["package_id"] == "aer_closure_ok"
    assert result["execution_mode"] == "execute"
    assert result["reason"] == "controlled_workspace_execution_completed"
    assert result["changed_files"] == ["workspace/aer_closure.txt"]
    assert result["audit_path"]
    assert result["evidence_path"]
    assert result["result_path"]
    assert result["final_message"] == "controlled_workspace_execution_completed"

    assert (tmp_path / "workspace/aer_closure.txt").read_text(encoding="utf-8") == "AER closure result\n"
    audit = json.loads((tmp_path / result["audit_path"]).read_text(encoding="utf-8"))
    evidence = json.loads((tmp_path / result["evidence_path"]).read_text(encoding="utf-8"))
    final = json.loads((tmp_path / result["result_path"]).read_text(encoding="utf-8"))
    scheduler_record = json.loads((tmp_path / "workspace/work_packages/aer_closure_ok.json").read_text(encoding="utf-8"))

    assert audit["status"] == "ok"
    assert evidence["target_path"] == "workspace/aer_closure.txt"
    assert final["status"] == "ok"
    assert final["final_message"] == "controlled_workspace_execution_completed"
    assert scheduler_record["status"] == "completed"
    assert scheduler_record["result"]["result_path"] == result["result_path"]
    assert response["execution"]["last_result"]["result_path"] == result["result_path"]


def test_aer_task_blocks_unsafe_path_and_still_returns_readable_result(tmp_path: Path) -> None:
    loop = AgentLoop(planner=Planner(), repo_root=str(tmp_path))

    response = loop.run(
        _aer_task_payload(
            repo_root=tmp_path,
            package_id="aer_closure_blocked",
            target_path="core/runtime/unsafe.py",
            content="bad\n",
            approval=True,
        )
    )

    assert response["ok"] is False
    assert response["mode"] == "work_package"
    assert response["package_id"] == "aer_closure_blocked"
    assert response["execution_mode"] == "execute"
    assert not (tmp_path / "core/runtime/unsafe.py").exists()

    result = response["work_package_result"]
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["blocked"] is True
    assert result["execution_mode"] == "execute"
    assert result["audit_path"]
    assert result["evidence_path"]
    assert result["result_path"]
    assert "blocked_target_prefix:core/runtime" in result["reason"]

    audit = json.loads((tmp_path / result["audit_path"]).read_text(encoding="utf-8"))
    final = json.loads((tmp_path / result["result_path"]).read_text(encoding="utf-8"))
    scheduler_record = json.loads((tmp_path / "workspace/work_packages/aer_closure_blocked.json").read_text(encoding="utf-8"))

    assert audit["status"] == "failed"
    assert audit["blocked"] is True
    assert final["status"] == "failed"
    assert final["result"]["reason"] == result["reason"]
    assert scheduler_record["status"] == "failed"
    assert scheduler_record["result"]["result_path"] == result["result_path"]


def test_aer_task_reads_input_and_writes_summary_and_action_items(tmp_path: Path) -> None:
    input_path = tmp_path / "workspace/input.txt"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(
        "ZERO needs to read a file, summarize it, then extract action items. "
        "Action: keep output paths exact.\n",
        encoding="utf-8",
    )
    loop = AgentLoop(planner=Planner(), repo_root=str(tmp_path))

    response = loop.run(
        json.dumps(
            {
                "task_type": "aer_task",
                "repo_root": str(tmp_path),
                "task_id": "aer_real_workspace_task",
                "goal": "Read workspace/input.txt and create workspace/summary.txt plus workspace/action_items.txt",
                "operation": "summarize_action_items",
                "source_path": "workspace/input.txt",
                "summary_path": "workspace/summary.txt",
                "action_items_path": "workspace/action_items.txt",
                "approval": True,
            }
        )
    )

    assert response["ok"] is True
    assert response["package_id"] == "aer_real_workspace_task"
    assert response["execution_mode"] == "execute"

    result = response["work_package_result"]
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["evidence_path"]
    assert result["result_path"]
    assert result["changed_files"] == ["workspace/summary.txt", "workspace/action_items.txt"]

    assert (tmp_path / "workspace/summary.txt").exists()
    assert (tmp_path / "workspace/action_items.txt").exists()
    assert "Summary: ZERO needs to read a file" in (tmp_path / "workspace/summary.txt").read_text(encoding="utf-8")
    assert "- keep output paths exact" in (tmp_path / "workspace/action_items.txt").read_text(encoding="utf-8")

    evidence = json.loads((tmp_path / result["evidence_path"]).read_text(encoding="utf-8"))
    final = json.loads((tmp_path / result["result_path"]).read_text(encoding="utf-8"))
    assert evidence["operation"] == "summarize_action_items"
    assert evidence["source_path"] == "workspace/input.txt"
    assert final["status"] == "ok"
    assert final["result"]["result"]["summary_path"] == "workspace/summary.txt"
