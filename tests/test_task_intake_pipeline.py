from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from core.runtime.runtime_contract_seal import build_runtime_contract_seal
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.task_runner import TaskRunner
from core.runtime.runtime_evidence_surface import list_evidence, register_evidence
from core.tasks.task_intake_contract import (
    TaskIntakeRequest,
    run_task_intake_pipeline,
)
from core.tasks.task_repository import TaskRepository


def test_task_intake_pipeline_accepts_engineering_task_and_tracks_outputs(
    tmp_path: Path,
) -> None:
    repo = TaskRepository(db_path=str(tmp_path / "workspace" / "tasks.json"))
    planner = RecordingPlanner()
    runtime = RecordingRuntime()
    executor = ArtifactExecutor(tmp_path)

    result = run_task_intake_pipeline(
        repo_root=tmp_path,
        request=TaskIntakeRequest(
            task_id="codex-phase-1",
            title="Codex Layer Phase 1",
            goal="Produce a tracked engineering artifact.",
        ),
        repository=repo,
        planner=planner,
        runtime=runtime,
        executor=executor,
    )
    payload = result.to_dict()
    stored_task = repo.get_task("codex-phase-1")
    artifact_path = Path(payload["artifacts"][0]["path"])
    evidence_items = list_evidence("codex-phase-1", repo_root=tmp_path)
    completion_path = Path(payload["evidence"]["evidence_path"])
    completion = json.loads(completion_path.read_text(encoding="utf-8"))

    assert payload["status"] == "done"
    assert stored_task is not None
    assert stored_task["status"] == "done"
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "Produce a tracked engineering artifact.\n"
    assert completion_path.exists()
    assert completion["status"] == "done"
    assert completion["artifacts"][0]["path"] == str(artifact_path)
    assert evidence_items[-1]["evidence_type"] == "task_report"
    assert evidence_items[-1]["path"] == str(completion_path)
    assert planner.task_ids == ["codex-phase-1"]
    assert runtime.plan_ids == ["plan-codex-phase-1"]
    assert executor.plan_ids == ["plan-codex-phase-1"]

    phases = [item["phase"] for item in payload["lifecycle"]]
    assert phases == [
        "task_created",
        "task_entered_repository",
        "planner_produced_plan",
        "runtime_received_plan",
        "executor_completed",
        "artifact_produced",
        "completion_report_created",
        "evidence_registered",
        "task_completed",
    ]
    assert "task_completed" in stored_task["history"]


def test_task_intake_evidence_does_not_break_runtime_contract_seal(tmp_path: Path) -> None:
    task_id = "codex-phase-1-seal"
    repo = TaskRepository(db_path=str(tmp_path / "workspace" / "tasks.json"))

    run_task_intake_pipeline(
        repo_root=tmp_path,
        request=TaskIntakeRequest(
            task_id=task_id,
            title="Seal compatibility",
            goal="Produce task report beside runtime contract evidence.",
        ),
        repository=repo,
        planner=RecordingPlanner(),
        runtime=RecordingRuntime(),
        executor=ArtifactExecutor(tmp_path),
    )
    _register_runtime_contract_chain_evidence(tmp_path, task_id)

    seal = build_runtime_contract_seal(task_id=task_id, repo_root=tmp_path)
    indexed_types = [item["evidence_type"] for item in list_evidence(task_id, repo_root=tmp_path)]

    assert seal.sealed is True
    assert seal.evidence_registry_status["ok"] is True
    assert "task_report" in indexed_types
    assert {"runtime_ownership", "runtime_execution_authority", "recovery_report", "runtime_transition", "mutation_audit"} <= set(indexed_types)


def test_task_intake_pipeline_adds_no_scheduler_agent_loop_or_authority_path() -> None:
    import core.runtime.artifact_completion_report as completion_report
    import core.tasks.task_intake_contract as intake_contract
    import core.tasks.task_intake_evidence as intake_evidence

    source = "\n".join(
        [
            inspect.getsource(intake_contract),
            inspect.getsource(intake_evidence),
            inspect.getsource(completion_report),
        ]
    )

    assert "from core.agent import agent_loop" not in source
    assert "from core.tasks import scheduler" not in source
    assert "from core.runtime.runtime_authority" not in source
    assert "from core.runtime.runtime_execution_authority" not in source
    assert "from core.runtime.runtime_contract_seal" not in source
    assert "RuntimeExecutionAuthorityGate" not in source
    assert "Executor(" not in source
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "bypass" not in source.lower()
    assert "fallback" not in source.lower()


def test_task_intake_fixture_cannot_complete_without_terminal_evidence() -> None:
    with pytest.raises(PermissionError, match="terminal_execution_evidence_required"):
        TaskRunner().complete_task({"task_id": "codex-phase-1", "steps": []})


class RecordingPlanner:
    def __init__(self) -> None:
        self.task_ids: list[str] = []

    def plan(self, *, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task["task_id"])
        self.task_ids.append(task_id)
        return {
            "schema": "codex_task_plan.v1",
            "plan_id": f"plan-{task_id}",
            "steps": [
                {
                    "step_id": f"{task_id}-artifact",
                    "kind": "artifact",
                    "goal": task["goal"],
                }
            ],
        }


class RecordingRuntime:
    def __init__(self) -> None:
        self.plan_ids: list[str] = []

    def receive_plan(self, *, task: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        self.plan_ids.append(str(plan["plan_id"]))
        return {
            "schema": "codex_runtime_plan_receipt.v1",
            "task_id": task["task_id"],
            "plan_id": plan["plan_id"],
            "status": "accepted",
        }


class ArtifactExecutor:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.plan_ids: list[str] = []

    def execute(
        self,
        *,
        task: dict[str, Any],
        plan: dict[str, Any],
        runtime_receipt: dict[str, Any],
    ) -> dict[str, Any]:
        self.plan_ids.append(str(runtime_receipt["plan_id"]))
        artifact_dir = self.repo_root / "workspace" / "artifacts" / str(task["task_id"])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "engineering_result.txt"
        artifact_path.write_text(str(task["goal"]) + "\n", encoding="utf-8")
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        runner = TaskRunner()
        completion_task = {
            "task_id": str(task["task_id"]),
            "package_id": f"{task['task_id']}-package",
            "session_id": str(runtime_receipt["plan_id"]),
        }
        completion_task["runtime_execution_capability"] = RuntimeDispatcher._execution_capability(completion_task)
        completion_step = {
            "id": f"{task['task_id']}-terminal",
            "type": "final_answer",
            "content": "engineering artifact produced",
        }
        completion_result = runner.execute_owned_step(completion_step, task=completion_task)
        completion_authority = runner._terminal_completion_authority(
            task=completion_task,
            step=completion_step,
            result=completion_result,
        )
        return {
            "schema": "codex_executor_result.v1",
            "status": "done",
            "task_completion_authority": completion_authority,
            "artifacts": [
                {
                    "artifact_id": f"{task['task_id']}:engineering_result",
                    "kind": "engineering_result",
                    "path": str(artifact_path),
                    "sha256": digest,
                }
            ],
        }


def _register_runtime_contract_chain_evidence(repo_root: Path, task_id: str) -> None:
    for evidence_type in (
        "runtime_ownership",
        "runtime_execution_authority",
        "recovery_report",
        "runtime_transition",
        "mutation_audit",
    ):
        artifact = repo_root / "workspace" / "evidence" / "contract_inputs" / f"{task_id}_{evidence_type}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps({"schema": f"{evidence_type}.test.v1", "task_id": task_id}) + "\n",
            encoding="utf-8",
        )
        register_evidence(
            task_id,
            evidence_type,
            artifact,
            {"schema": f"{evidence_type}.test.v1"},
            repo_root=repo_root,
        )
