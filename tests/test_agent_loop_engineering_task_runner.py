from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop


def _engineering_payload(
    *,
    repo_root: Path,
    package_id: str,
    target_path: str,
    content: str,
    verify_contains: str | None = None,
) -> str:
    return json.dumps(
        {
            "task_type": "engineering_task",
            "repo_root": str(repo_root),
            "task_id": package_id,
            "goal": f"Run engineering task for {target_path}",
            "mode": "execute",
            "approval": True,
            "acceptance": [
                "requirement summary generated",
                "edit plan generated",
                "impact analysis generated",
                "change set generated",
                "verification result included",
                "rollback status included",
            ],
            "edits": [
                {
                    "operation": "write_file",
                    "target_path": target_path,
                    "content": content,
                    "verify_contains": verify_contains or content.strip(),
                }
            ],
        }
    )


def test_agent_loop_receives_engineering_task_payload(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        _engineering_payload(
            repo_root=tmp_path,
            package_id="agent_loop_engineering_received",
            target_path="workspace/agent_loop_engineering_received.txt",
            content="AgentLoop received engineering task.\n",
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    assert response["package_id"] == "agent_loop_engineering_received"
    assert (tmp_path / "workspace/agent_loop_engineering_received.txt").read_text(encoding="utf-8") == (
        "AgentLoop received engineering task.\n"
    )


def test_agent_loop_delegates_to_engineering_task_runner(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_engineering_task(payload, *, repo_root):
        calls.append({"payload": payload, "repo_root": repo_root})
        return {
            "schema": "zero.engineering_task_runner.v1",
            "ok": True,
            "mode": "engineering_task_runner",
            "package_id": "agent_loop_delegate_probe",
            "requirement_summary": {"schema": "zero.engineering_task.requirement_summary.v1"},
            "normalized_payload": {"schema": "zero.engineering_task.normalized_payload.v1"},
            "result_bundle": {
                "schema": "zero.engineering_task.result_bundle.v1",
                "ok": True,
                "artifact_paths": {},
                "execution_path": {
                    "no_new_runtime_path": True,
                    "direct_write_shortcut": False,
                },
            },
            "work_package_result": {"ok": True, "reason": "delegated"},
            "verification_result": {"ok": True},
            "change_set": {"change_set_id": "change_set:agent_loop_delegate_probe"},
            "final_message": "delegated",
        }

    monkeypatch.setattr("core.tasks.engineering_task_runner.run_engineering_task", fake_run_engineering_task)

    loop = AgentLoop(repo_root=str(tmp_path))
    response = loop.run(
        _engineering_payload(
            repo_root=tmp_path,
            package_id="agent_loop_delegate_probe",
            target_path="workspace/delegate_probe.txt",
            content="delegate probe\n",
        )
    )

    assert calls == [
        {
            "payload": json.loads(
                _engineering_payload(
                    repo_root=tmp_path,
                    package_id="agent_loop_delegate_probe",
                    target_path="workspace/delegate_probe.txt",
                    content="delegate probe\n",
                )
            ),
            "repo_root": str(tmp_path),
        }
    ]
    assert response["ok"] is True
    assert response["result_bundle"]["schema"] == "zero.engineering_task.result_bundle.v1"
    assert response["plan"]["delegated_to"] == "core.tasks.engineering_task_runner.run_engineering_task"


def test_agent_loop_engineering_task_result_bundle_visible_to_caller(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        _engineering_payload(
            repo_root=tmp_path,
            package_id="agent_loop_engineering_bundle",
            target_path="workspace/agent_loop_engineering_bundle.txt",
            content="AgentLoop result bundle is visible.\n",
        )
    )

    bundle = response["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.result_bundle.v1"
    assert bundle["requirement_summary"] == response["requirement_summary"]
    assert bundle["edit_plan"]
    assert bundle["impact_analysis"]
    assert bundle["change_set"]
    assert bundle["verification_result"]["ok"] is True
    assert bundle["rollback_status"]["rollback_performed"] is False
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert response["change_set"]["change_set_id"] == "change_set:agent_loop_engineering_bundle"
    assert response["work_package_result"]["result_path"] == bundle["artifact_paths"]["result_path"]
    assert (tmp_path / bundle["artifact_paths"]["result_path"]).exists()
    assert (tmp_path / bundle["artifact_paths"]["evidence_path"]).exists()


def test_real_engineering_task_enters_agent_loop_and_returns_verified_aer_bundle(tmp_path: Path) -> None:
    target = tmp_path / "workspace/agent_loop_real_e2e_target.txt"

    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        _engineering_payload(
            repo_root=tmp_path,
            package_id="agent_loop_real_engineering_e2e",
            target_path="workspace/agent_loop_real_e2e_target.txt",
            content="verified through aer\n",
            verify_contains="verified through aer",
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    assert response["route"]["authority_path"] == (
        "AgentLoop -> EngineeringTaskRunner -> Planner -> WorkPackageScheduler -> WorkPackageIntake"
    )

    bundle = response["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.result_bundle.v1"
    assert bundle["normalized_payload"]["normalizer"] == "Planner.normalize_aer_execution_intent"
    assert bundle["scheduler_record"]["schema"] == "zero.work_package.scheduler.v5_1"
    assert bundle["work_package_result"]["schema"] == "zero.work_package.intake_result.v6_4"
    assert bundle["work_package_result"]["reason"] == "controlled_multi_file_write_completed"
    assert bundle["verification_result"]["ok"] is True
    assert bundle["verification_set"]["ok"] is True
    assert bundle["rollback_status"]["rollback_performed"] is False
    assert bundle["change_set"]["successful"] is True
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert "WorkPackageIntake._execute_controlled_multi_write" in bundle["execution_path"]["existing_controlled_edit_path"]
    assert "WorkPackageScheduler.submit" in bundle["execution_path"]["existing_aer_work_package_path"]
    assert target.read_text(encoding="utf-8") == "verified through aer\n"


def test_agent_loop_engineering_task_blocked_task_still_blocked(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        _engineering_payload(
            repo_root=tmp_path,
            package_id="agent_loop_engineering_blocked",
            target_path="core/runtime/agent_loop_blocked.py",
            content="bad\n",
            verify_contains="bad",
        )
    )

    assert response["ok"] is False
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    assert not (tmp_path / "core/runtime/agent_loop_blocked.py").exists()

    result = response["work_package_result"]
    bundle = response["result_bundle"]
    assert result["blocked"] is True
    assert "blocked_target_prefix:core/runtime" in result["reason"]
    assert bundle["change_set"]["successful"] is False
    assert bundle["change_set"]["execution_result"]["status"] == "blocked"
    assert bundle["verification_result"]["ok"] is False
    assert bundle["rollback_status"]["rollback_performed"] is False
