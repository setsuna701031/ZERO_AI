from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Mapping

from core.planning.planner import Planner
from core.runtime.multistep_task_report import (
    build_multistep_task_report,
    export_multistep_task_report_evidence,
)
from core.runtime.runtime_contract_seal import build_runtime_contract_seal
from core.runtime.runtime_evidence_surface import list_evidence, register_evidence
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from tests.authority_test_support import owned_step_executor
from core.tasks.task_repository import TaskRepository


def test_multistep_engineering_task_runs_real_planner_runtime_and_artifacts(
    tmp_path: Path,
) -> None:
    task_id = "phase-2-multistep"
    workspace_root = tmp_path / "workspace"
    repo = TaskRepository(db_path=str(workspace_root / "tasks.json"))
    task = _create_real_task(repo, task_id=task_id)

    planner = Planner(workspace_root=str(workspace_root))
    plan = planner.plan(
        user_input=(
            f"write alpha to workspace/artifacts/multistep/{task_id}/alpha.txt; "
            f"write beta to workspace/artifacts/multistep/{task_id}/beta.txt; "
            f"write gamma to workspace/artifacts/multistep/{task_id}/gamma.txt"
        ),
        context={"repo_root": str(tmp_path), "workspace_root": str(workspace_root)},
    )
    steps = plan.get("steps")

    assert plan.get("ok") is True
    assert plan.get("meta", {}).get("fallback_used") is False
    assert isinstance(steps, list)
    assert len(steps) >= 3

    lifecycle = [
        _event("task_created", task_id, status="created"),
        _event("task_entered_repository", task_id, status="queued"),
        _event("planner_produced_multistep_plan", task_id, status="planned", step_count=len(steps)),
    ]
    execution_result = owned_step_executor(workspace_root=str(workspace_root)).execute_steps(
        steps,
        task=task,
        context={"repo_root": str(tmp_path), "workspace_root": str(workspace_root)},
    )
    lifecycle.append(
        _event(
            "runtime_executed_multistep_plan",
            task_id,
            status="executed",
            completed_steps=execution_result.get("completed_steps"),
        )
    )
    artifacts = _collect_artifacts(execution_result)
    lifecycle.append(
        _event("artifacts_produced", task_id, status="recorded", artifact_count=len(artifacts))
    )

    assert execution_result["ok"] is True
    assert execution_result["completed_steps"] == len(steps)
    assert len(artifacts) >= 3

    expected = {
        tmp_path / "workspace" / "artifacts" / "multistep" / task_id / "alpha.txt": "alpha",
        tmp_path / "workspace" / "artifacts" / "multistep" / task_id / "beta.txt": "beta",
        tmp_path / "workspace" / "artifacts" / "multistep" / task_id / "gamma.txt": "gamma",
    }
    for path, text in expected.items():
        assert path.exists()
        assert path.read_text(encoding="utf-8") == text

    report = build_multistep_task_report(
        task_id=task_id,
        status="finished",
        lifecycle=lifecycle,
        plan=plan,
        execution_result=execution_result,
        artifacts=artifacts,
        metadata={"planner_mode": plan.get("planner_mode")},
    )
    lifecycle.append(_event("completion_report_created", task_id, status="reported"))
    report = build_multistep_task_report(
        task_id=task_id,
        status="finished",
        lifecycle=lifecycle,
        plan=plan,
        execution_result=execution_result,
        artifacts=artifacts,
        metadata={"planner_mode": plan.get("planner_mode")},
    )
    evidence = export_multistep_task_report_evidence(
        repo_root=tmp_path,
        task_id=task_id,
        report=report,
    )
    lifecycle.append(_event("evidence_registered", task_id, status="indexed"))
    lifecycle.append(_event("task_finished", task_id, status="finished"))
    final_report = build_multistep_task_report(
        task_id=task_id,
        status="finished",
        lifecycle=lifecycle,
        plan=plan,
        execution_result=execution_result,
        artifacts=artifacts,
        metadata={"planner_mode": plan.get("planner_mode")},
    )
    evidence = export_multistep_task_report_evidence(
        repo_root=tmp_path,
        task_id=task_id,
        report=final_report,
    )

    finished_task = {
        **task,
        "status": "finished",
        "steps": steps,
        "steps_total": len(steps),
        "current_step_index": len(steps),
        "artifacts": artifacts,
        "completion_report": {
            "path": evidence["evidence_path"],
            "fingerprint": final_report.fingerprint,
        },
        "history": [item["phase"] for item in lifecycle],
        "result": {
            "status": "finished",
            "artifact_count": len(artifacts),
            "completion_report_path": evidence["evidence_path"],
        },
    }
    completion_authority = TaskRunner().complete_task(
        {"task_id": task_id, "steps": []}
    )["task_completion_authority"]
    repo.upsert_task(finished_task, completion_authority=completion_authority)
    stored = repo.get_task(task_id)
    indexed = list_evidence(task_id, repo_root=tmp_path)
    completion_payload = json.loads(Path(evidence["evidence_path"]).read_text(encoding="utf-8"))

    assert stored is not None
    assert stored["status"] == "finished"
    assert stored["steps_total"] == len(steps)
    assert stored["current_step_index"] == len(steps)
    assert stored["artifacts"] == artifacts
    assert Path(stored["completion_report"]["path"]).exists()
    assert completion_payload["status"] == "finished"
    assert completion_payload["execution_result"]["ok"] is True
    assert completion_payload["metadata"]["no_runtime_core_capability_added"] is True
    assert [item["phase"] for item in completion_payload["lifecycle"]] == [
        "task_created",
        "task_entered_repository",
        "planner_produced_multistep_plan",
        "runtime_executed_multistep_plan",
        "artifacts_produced",
        "completion_report_created",
        "evidence_registered",
        "task_finished",
    ]
    assert indexed[-1]["evidence_type"] == "task_report"
    assert indexed[-1]["metadata"]["report_type"] == "multistep_engineering_task_report"


def test_multistep_task_report_evidence_does_not_break_runtime_contract_seal(
    tmp_path: Path,
) -> None:
    task_id = "phase-2-contract-compatible"
    report = build_multistep_task_report(
        task_id=task_id,
        status="finished",
        lifecycle=[_event("task_finished", task_id, status="finished")],
        plan={"ok": True, "steps": [{"type": "write_file"}]},
        execution_result={"ok": True, "step_count": 1, "completed_steps": 1},
        artifacts=[{"artifact_id": "artifact-1", "path": str(tmp_path / "artifact.txt")}],
    )
    export_multistep_task_report_evidence(repo_root=tmp_path, task_id=task_id, report=report)
    _register_runtime_contract_chain_evidence(tmp_path, task_id)

    seal = build_runtime_contract_seal(task_id=task_id, repo_root=tmp_path)
    indexed_types = [item["evidence_type"] for item in list_evidence(task_id, repo_root=tmp_path)]

    assert seal.sealed is True
    assert "task_report" in indexed_types


def test_multistep_task_report_adds_no_scheduler_agent_loop_or_contract_runtime_changes() -> None:
    import core.runtime.multistep_task_report as multistep_report

    source = inspect.getsource(multistep_report)

    assert "from core.agent import agent_loop" not in source
    assert "from core.tasks import scheduler" not in source
    assert "from core.runtime.runtime_authority" not in source
    assert "from core.runtime.runtime_contract_seal" not in source
    assert "RuntimeExecutionAuthorityGate" not in source
    assert "StepExecutor" not in source
    assert "subprocess" not in source
    assert "os.system" not in source


def _create_real_task(repo: TaskRepository, *, task_id: str) -> dict[str, Any]:
    task = {
        "task_id": task_id,
        "title": "Codex Layer Phase 2 multistep task",
        "goal": "Produce three tracked engineering artifacts through real planner/runtime execution.",
        "task_type": "engineering",
        "status": "queued",
        "history": ["created", "queued"],
    }
    repo.add_task(task)
    stored = repo.get_task(task_id)
    assert stored is not None
    return stored


def _collect_artifacts(execution_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in execution_result.get("results") or []:
        if not isinstance(item, Mapping):
            continue
        result = item.get("result")
        if not isinstance(result, Mapping):
            continue
        nested = result.get("result")
        if not isinstance(nested, Mapping):
            continue
        full_path = str(nested.get("full_path") or nested.get("path") or "").strip()
        if not full_path or full_path in seen_paths:
            continue
        if str(nested.get("type") or "").strip().lower() not in {"write_file", "ensure_file", "append_file"}:
            continue
        path = Path(full_path)
        if not path.exists() or not path.is_file():
            continue
        artifacts.append(
            {
                "artifact_id": f"artifact-{len(artifacts) + 1}",
                "kind": str(nested.get("type") or "file"),
                "path": str(path),
                "bytes": path.stat().st_size,
            }
        )
        seen_paths.add(full_path)
    return artifacts


def _event(phase: str, task_id: str, *, status: str, **extra: Any) -> dict[str, Any]:
    item = {
        "task_id": task_id,
        "phase": phase,
        "status": status,
    }
    item.update(extra)
    return item


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
