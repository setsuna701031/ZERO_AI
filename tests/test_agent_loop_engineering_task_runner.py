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


def _multi_step_payload(
    repo_root: Path,
    *,
    blocked: bool = False,
    task_id: str | None = None,
    resume: bool = False,
    interrupt_after_step: int = 0,
) -> str:
    return json.dumps(
        {
            "task_type": "engineering_task",
            "repo_root": str(repo_root),
            "task_id": task_id or ("agent_loop_multi_step_blocked" if blocked else "agent_loop_multi_step_e2e"),
            "goal": "Run a multi-step engineering task through AgentLoop",
            "mode": "execute",
            "approval": True,
            "resume": resume,
            "interrupt_after_step": interrupt_after_step,
            "acceptance": [
                "multi-step task enters AgentLoop",
                "first step produces result_bundle",
                "observation is recorded",
                "next step is derived from observation",
                "final result includes all step results",
                "blocked step stops safely",
            ],
            "steps": [
                {
                    "package_id": "agent_loop_multi_step_first",
                    "goal": "Write first full-file output",
                    "edits": [
                        {
                            "operation": "write_file",
                            "target_path": "workspace/agent_loop_multi_step_first.txt",
                            "content": "first full-file output\n",
                            "verify_contains": "first full-file output",
                        }
                    ],
                },
                {
                    "package_id": "agent_loop_multi_step_second_blocked" if blocked else "agent_loop_multi_step_second",
                    "goal": "Write second full-file output from observation",
                    "derive_from_observation": {
                        "content_template": "derived from {first_changed_file}\n",
                        "verify_contains_template": "derived from {first_changed_file}",
                    },
                    "edits": [
                        {
                            "operation": "write_file",
                            "target_path": "core/runtime/agent_loop_multi_step_blocked.py" if blocked else "workspace/agent_loop_multi_step_second.txt",
                            "content": "placeholder replaced by observation\n",
                            "verify_contains": "placeholder",
                        }
                    ],
                },
                {
                    "package_id": "agent_loop_multi_step_never_runs" if blocked else "agent_loop_multi_step_third",
                    "goal": "This step should not run after a blocked step" if blocked else "Write third full-file output",
                    "edits": [
                        {
                            "operation": "write_file",
                            "target_path": "workspace/agent_loop_multi_step_never_runs.txt",
                            "content": "should not exist\n",
                            "verify_contains": "should not exist",
                        }
                    ],
                },
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


def test_multi_step_engineering_task_enters_agent_loop_and_completes_with_result_bundle(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(_multi_step_payload(tmp_path))

    assert response["ok"] is True
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    assert response["route"]["authority_path"] == (
        "AgentLoop -> EngineeringTaskRunner -> Planner -> WorkPackageScheduler -> WorkPackageIntake"
    )

    bundle = response["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.multi_step_result_bundle.v1"
    assert bundle["multi_step_plan"]["schema"] == "zero.engineering_task.multi_step_plan.v1"
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert bundle["execution_path"]["full_file_outputs_only"] is True

    step_results = bundle["step_results"]
    assert len(step_results) == 3
    assert step_results[0]["result"]["result_bundle"]["schema"] == "zero.engineering_task.result_bundle.v1"
    assert step_results[0]["result"]["result_bundle"]["execution_path"]["no_new_runtime_path"] is True
    assert step_results[0]["result"]["result_bundle"]["execution_path"]["direct_write_shortcut"] is False

    observations = bundle["observations"]
    assert len(observations) == 3
    assert observations[0]["schema"] == "zero.engineering_task.step_observation.v1"
    assert observations[0]["changed_files"] == ["workspace/agent_loop_multi_step_first.txt"]
    decisions = bundle["decisions"]
    assert len(decisions) == 3
    assert decisions[0]["schema"] == "zero.engineering_task.observation_decision.v1"
    assert decisions[0]["decision"] == "continue"
    assert decisions[0]["next_action"] == "continue"

    second_payload = step_results[1]["step_payload"]
    assert second_payload["metadata"]["derived_from_observation"] is True
    assert second_payload["edits"][0]["content"] == "derived from workspace/agent_loop_multi_step_first.txt\n"
    assert step_results[1]["derived_from_observation"] is True
    assert bundle["replans"][0]["schema"] == "zero.engineering_task.continuation_plan.v1"
    assert bundle["replans"][0]["derived_from_observation"] is True

    assert bundle["verification_result"]["ok"] is True
    assert bundle["change_set"]["successful"] is True
    assert len(bundle["step_results"]) == 3
    assert response["step_results"] == bundle["step_results"]
    assert response["observations"] == bundle["observations"]
    assert response["decisions"] == bundle["decisions"]
    assert (tmp_path / "workspace/agent_loop_multi_step_first.txt").read_text(encoding="utf-8") == "first full-file output\n"
    assert (tmp_path / "workspace/agent_loop_multi_step_second.txt").read_text(encoding="utf-8") == (
        "derived from workspace/agent_loop_multi_step_first.txt\n"
    )
    assert (tmp_path / "workspace/agent_loop_multi_step_never_runs.txt").read_text(encoding="utf-8") == "should not exist\n"


def test_multi_step_engineering_task_blocked_step_stops_safely(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(_multi_step_payload(tmp_path, blocked=True))

    assert response["ok"] is False
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"

    bundle = response["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.multi_step_result_bundle.v1"
    assert len(bundle["step_results"]) == 2
    assert len(bundle["observations"]) == 2
    assert bundle["observations"][1]["status"] == "blocked"
    assert bundle["observations"][1]["next_action"] == "stop_safely"
    assert bundle["decisions"][1]["decision"] == "stop_safely"
    assert bundle["decisions"][1]["next_action"] == "stop_safely"
    assert bundle["replans"][-1]["decision"] == "stop_safely"
    assert bundle["replans"][-1]["blocked_step_stops_safely"] is True
    assert "blocked_target_prefix:core/runtime" in bundle["stopped_reason"]
    assert bundle["step_results"][1]["result"]["result_bundle"]["rollback_status"]["rollback_performed"] is False
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert (tmp_path / "workspace/agent_loop_multi_step_first.txt").exists()
    assert not (tmp_path / "core/runtime/agent_loop_multi_step_blocked.py").exists()
    assert not (tmp_path / "workspace/agent_loop_multi_step_never_runs.txt").exists()


def test_multi_step_engineering_task_replans_next_step_from_observation(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        json.dumps(
            {
                "task_type": "engineering_task",
                "repo_root": str(tmp_path),
                "task_id": "agent_loop_adaptive_replan",
                "goal": "Adapt next step after observing first result",
                "mode": "execute",
                "approval": True,
                "steps": [
                    {
                        "package_id": "agent_loop_adaptive_replan_first",
                        "goal": "Write source observation file",
                        "edits": [
                            {
                                "operation": "write_file",
                                "target_path": "workspace/agent_loop_adaptive_source.txt",
                                "content": "adaptive source\n",
                                "verify_contains": "adaptive source",
                            }
                        ],
                    },
                    {
                        "package_id": "agent_loop_adaptive_replan_second",
                        "goal": "This goal is replaced by observation replan",
                        "replan_from_observation": {
                            "goal_template": "Replanned after {previous_package_id}",
                            "target_path_template": "workspace/replanned_from_{previous_package_id}.txt",
                            "content_template": "replanned from {first_changed_file}\n",
                            "verify_contains_template": "replanned from {first_changed_file}",
                            "reason_template": "observed {first_changed_file}",
                        },
                        "edits": [
                            {
                                "operation": "write_file",
                                "target_path": "workspace/agent_loop_adaptive_original_target.txt",
                                "content": "original next step\n",
                                "verify_contains": "original next step",
                            }
                        ],
                    },
                ],
            }
        )
    )

    assert response["ok"] is True
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    bundle = response["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.multi_step_result_bundle.v1"
    assert bundle["decisions"][0]["decision"] == "replan_next_step"
    assert bundle["decisions"][0]["next_action"] == "replan"
    assert bundle["decisions"][0]["replanned"] is True
    assert bundle["replans"][0]["decision"] == "replan_next_step"
    assert bundle["replans"][0]["existing_aer_path_preserved"] is True

    second = bundle["step_results"][1]
    second_payload = second["step_payload"]
    assert second_payload["goal"] == "Replanned after agent_loop_adaptive_replan_first"
    assert second_payload["metadata"]["replanned_from_observation"] is True
    assert second_payload["edits"][0]["target_path"] == "workspace/replanned_from_agent_loop_adaptive_replan_first.txt"
    assert second["result"]["result_bundle"]["execution_path"]["no_new_runtime_path"] is True
    assert second["result"]["result_bundle"]["execution_path"]["direct_write_shortcut"] is False
    assert second["result"]["result_bundle"]["change_set"]["files"] == [
        "workspace/replanned_from_agent_loop_adaptive_replan_first.txt"
    ]
    assert (tmp_path / "workspace/replanned_from_agent_loop_adaptive_replan_first.txt").read_text(encoding="utf-8") == (
        "replanned from workspace/agent_loop_adaptive_source.txt\n"
    )
    assert not (tmp_path / "workspace/agent_loop_adaptive_original_target.txt").exists()


def test_multi_step_engineering_task_failed_observation_stops_before_next_step(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path))

    response = loop.run(
        json.dumps(
            {
                "task_type": "engineering_task",
                "repo_root": str(tmp_path),
                "task_id": "agent_loop_adaptive_failed_observation",
                "goal": "Stop safely when a step fails verification",
                "mode": "execute",
                "approval": True,
                "steps": [
                    {
                        "package_id": "agent_loop_adaptive_failed_first",
                        "goal": "Write file that fails verification",
                        "edits": [
                            {
                                "operation": "write_file",
                                "target_path": "workspace/agent_loop_adaptive_failed_first.txt",
                                "content": "temporary failed content\n",
                                "verify_contains": "missing verification marker",
                            }
                        ],
                    },
                    {
                        "package_id": "agent_loop_adaptive_should_not_run",
                        "goal": "This step must not execute",
                        "edits": [
                            {
                                "operation": "write_file",
                                "target_path": "workspace/agent_loop_adaptive_should_not_run.txt",
                                "content": "should not run\n",
                                "verify_contains": "should not run",
                            }
                        ],
                    },
                ],
            }
        )
    )

    assert response["ok"] is False
    bundle = response["result_bundle"]
    assert len(bundle["observations"]) == 1
    assert len(bundle["decisions"]) == 1
    assert bundle["observations"][0]["status"] == "failed"
    assert bundle["decisions"][0]["decision"] == "stop_safely"
    assert bundle["decisions"][0]["existing_rollback_preserved"] is True
    assert bundle["replans"][-1]["decision"] == "stop_safely"
    assert bundle["step_results"][0]["result"]["result_bundle"]["rollback_status"]["rollback_performed"] is True
    assert not (tmp_path / "workspace/agent_loop_adaptive_failed_first.txt").exists()
    assert not (tmp_path / "workspace/agent_loop_adaptive_should_not_run.txt").exists()


def test_multi_step_engineering_task_persists_and_resumes_without_rerunning_completed_steps(tmp_path: Path) -> None:
    task_id = "agent_loop_multi_step_resume"
    loop = AgentLoop(repo_root=str(tmp_path))

    interrupted = loop.run(_multi_step_payload(tmp_path, task_id=task_id, interrupt_after_step=1))

    assert interrupted["ok"] is False
    assert interrupted["interrupted"] is True
    assert interrupted["resumed"] is False
    assert interrupted["result_bundle"]["interrupted"] is True
    assert interrupted["result_bundle"]["state_saved_after_each_step"] is True
    assert len(interrupted["result_bundle"]["step_results"]) == 1

    state_path = tmp_path / interrupted["state_path"]
    assert state_path.exists()
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved_state["schema"] == "zero.engineering_task.multi_step_state.v1"
    assert saved_state["status"] == "interrupted"
    assert saved_state["completed_step_count"] == 1
    assert saved_state["next_step_index"] == 2

    first_step_record_path = tmp_path / "workspace/work_packages/agent_loop_multi_step_first.json"
    first_step_record_before = json.loads(first_step_record_path.read_text(encoding="utf-8"))

    resumed = loop.run(_multi_step_payload(tmp_path, task_id=task_id, resume=True))

    assert resumed["ok"] is True
    assert resumed["resumed"] is True
    assert resumed["interrupted"] is False
    bundle = resumed["result_bundle"]
    assert bundle["resumed"] is True
    assert bundle["interrupted"] is False
    assert len(bundle["step_results"]) == 3
    assert bundle["step_results"][0] == interrupted["result_bundle"]["step_results"][0]
    assert bundle["verification_result"]["ok"] is True
    assert bundle["change_set"]["successful"] is True
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False

    first_step_record_after = json.loads(first_step_record_path.read_text(encoding="utf-8"))
    assert first_step_record_after == first_step_record_before

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert final_state["status"] == "completed"
    assert final_state["completed_step_count"] == 3
    assert final_state["next_step_index"] == 4
    assert final_state["resumed"] is True
    assert (tmp_path / "workspace/agent_loop_multi_step_second.txt").exists()
    assert (tmp_path / "workspace/agent_loop_multi_step_never_runs.txt").exists()


def test_multi_step_engineering_task_resume_blocked_step_stops_safely(tmp_path: Path) -> None:
    task_id = "agent_loop_multi_step_resume_blocked"
    loop = AgentLoop(repo_root=str(tmp_path))

    interrupted = loop.run(_multi_step_payload(tmp_path, task_id=task_id, interrupt_after_step=1))
    assert interrupted["interrupted"] is True
    assert len(interrupted["result_bundle"]["step_results"]) == 1

    resumed = loop.run(_multi_step_payload(tmp_path, task_id=task_id, blocked=True, resume=True))

    assert resumed["ok"] is False
    assert resumed["resumed"] is True
    bundle = resumed["result_bundle"]
    assert bundle["resumed"] is True
    assert len(bundle["step_results"]) == 2
    assert bundle["step_results"][0] == interrupted["result_bundle"]["step_results"][0]
    assert bundle["observations"][1]["status"] == "blocked"
    assert bundle["observations"][1]["next_action"] == "stop_safely"
    assert bundle["replans"][-1]["decision"] == "stop_safely"
    assert "blocked_target_prefix:core/runtime" in bundle["stopped_reason"]
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert not (tmp_path / "core/runtime/agent_loop_multi_step_blocked.py").exists()
    assert not (tmp_path / "workspace/agent_loop_multi_step_never_runs.txt").exists()

    final_state = json.loads((tmp_path / resumed["state_path"]).read_text(encoding="utf-8"))
    assert final_state["status"] == "blocked_or_failed"
    assert final_state["completed_step_count"] == 2
    assert final_state["resumed"] is True


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
