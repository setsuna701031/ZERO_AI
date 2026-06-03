from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_memory_store import EngineeringMemoryStore
from core.tasks.engineering_task_runner import run_engineering_task


def _completed_payload(task_id: str, goal: str, target_path: str) -> dict:
    return {
        "task_type": "engineering_task",
        "task_id": task_id,
        "package_id": task_id,
        "goal": goal,
        "mode": "execute",
        "approval": True,
        "acceptance_criteria": [f"{target_path} is written"],
        "steps": [
            {
                "package_id": f"{task_id}_write",
                "goal": f"Write {target_path}",
                "edits": [
                    {
                        "operation": "write_file",
                        "target_path": target_path,
                        "content": f"{goal}\n",
                        "verify_contains": goal,
                    }
                ],
            }
        ],
    }


def test_engineering_memory_record_saved_and_retrieved_deterministically(tmp_path: Path) -> None:
    first = run_engineering_task(
        _completed_payload(
            "memory_auth_contract",
            "Persist authentication retry decision memory",
            "workspace/memory_auth_contract.txt",
        ),
        repo_root=tmp_path,
    )

    assert first["ok"] is True
    record = first["memory_record"]
    assert record["schema"] == "zero.engineering_task.memory_record.v1"
    assert record["task_id"] == "memory_auth_contract"
    assert record["goal"] == "Persist authentication retry decision memory"
    assert record["observations"]
    assert record["decisions"]
    assert record["acceptance_criteria"] == ["workspace/memory_auth_contract.txt is written"]

    store = EngineeringMemoryStore(tmp_path)
    retrieval_one = store.load_relevant_memory(goal="Use authentication retry decision memory")
    retrieval_two = store.load_relevant_memory(goal="Use authentication retry decision memory")

    assert retrieval_one == retrieval_two
    assert retrieval_one["deterministic"] is True
    assert retrieval_one["retrieval_methods"] == ["keyword", "goal_similarity"]
    assert retrieval_one["records"][0]["task_id"] == "memory_auth_contract"


def test_retrieved_memory_visible_to_bundle_candidates_and_prioritization(tmp_path: Path) -> None:
    run_engineering_task(
        _completed_payload(
            "memory_candidate_source",
            "Reusable cache migration ordering memory",
            "workspace/memory_candidate_source.txt",
        ),
        repo_root=tmp_path,
    )

    second = run_engineering_task(
        {
            "task_type": "engineering_task",
            "task_id": "memory_candidate_consumer",
            "package_id": "memory_candidate_consumer",
            "goal": "Use cache migration ordering memory before planning",
            "mode": "execute",
            "approval": True,
            "steps": [
                {
                    "package_id": "memory_candidate_consumer_seed",
                    "goal": "Write seed file",
                    "edits": [
                        {
                            "operation": "write_file",
                            "target_path": "workspace/memory_candidate_consumer_seed.txt",
                            "content": "seed\n",
                            "verify_contains": "seed",
                        }
                    ],
                },
                {
                    "package_id": "memory_candidate_selector",
                    "goal": "Select next task using memory",
                    "candidate_tasks_from_observation": [
                        {
                            "package_id": "memory_candidate_blocked",
                            "goal": "Blocked cache migration candidate",
                            "metadata": {"risk_score": 1, "cost_score": 1, "value_score": 500},
                            "edits": [
                                {
                                    "operation": "write_file",
                                    "target_path": "core/runtime/memory_candidate_blocked.py",
                                    "content": "blocked\n",
                                    "verify_contains": "blocked",
                                }
                            ],
                        },
                        {
                            "package_id": "memory_candidate_selected",
                            "goal": "Selected cache migration candidate",
                            "metadata": {"risk_score": 5, "cost_score": 5, "value_score": 100},
                            "edits": [
                                {
                                    "operation": "write_file",
                                    "target_path": "workspace/memory_candidate_selected.txt",
                                    "content": "selected\n",
                                    "verify_contains": "selected",
                                }
                            ],
                        },
                    ],
                },
            ],
        },
        repo_root=tmp_path,
    )

    assert second["ok"] is True
    bundle = second["result_bundle"]
    assert bundle["relevant_memory"]["records"][0]["task_id"] == "memory_candidate_source"
    assert bundle["retrieved_memory"] == bundle["relevant_memory"]
    assert bundle["generated_tasks"][0]["memory_visible_to_candidate_generation"] is True
    assert bundle["candidate_tasks"][0]["memory_visible_to_candidate_generation"] is True
    assert bundle["candidate_evaluations"][0]["memory_visible_to_prioritization"] is True
    assert bundle["prioritization_data"]["memory_visible_to_prioritization"] is True
    assert bundle["prioritization_data"]["relevant_memory"]["records"][0]["task_id"] == "memory_candidate_source"
    assert bundle["selected_task"]["package_id"] == "memory_candidate_selected"
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
    assert "WorkPackageScheduler.submit" in bundle["execution_path"]["existing_aer_work_package_path"]


def test_blocked_memory_record_ignored(tmp_path: Path) -> None:
    store = EngineeringMemoryStore(tmp_path)
    store.save_record(
        {
            "task_id": "blocked_memory",
            "goal": "Blocked cache migration memory",
            "status": "blocked",
            "ok": True,
            "result_summary": {"status": "blocked"},
        }
    )
    store.save_record(
        {
            "task_id": "completed_memory",
            "goal": "Completed cache migration memory",
            "status": "completed",
            "ok": True,
            "result_summary": {"status": "completed"},
        }
    )

    retrieval = store.load_relevant_memory(goal="cache migration memory")
    task_ids = [record["task_id"] for record in retrieval["records"]]

    assert "completed_memory" in task_ids
    assert "blocked_memory" not in task_ids
    assert retrieval["ignored_blocked_records"] is True
