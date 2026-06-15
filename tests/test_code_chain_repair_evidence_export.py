from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.agent.code_chain_repair_evidence import export_code_chain_repair_evidence
from core.runtime.step_executor import StepExecutor
from core.runtime.runtime_evidence_surface import list_evidence


class RepairEvidencePlanner:
    def __init__(self, *, target_path: str, repo_root: Path) -> None:
        self.target_path = target_path
        self.repo_root = repo_root
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        context = context if isinstance(context, dict) else {}
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        if context.get("repair_loop"):
            return self._repair_plan()
        return self._failing_plan()

    def _route_metadata(self) -> dict:
        return {
            "code_chain_intent": True,
            "route": "code_chain_controlled_self_edit",
            "task_kind": "code_fix",
            "requires_controlled_mutation": True,
        }

    def _failing_plan(self) -> dict:
        return {
            "ok": True,
            "goal": "Initial edit fails verification before repair evidence export",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "first attempt leaves verifier unsatisfied",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": 'return "broken"',
                        "new_text": 'return "almost_fixed"',
                    },
                    "verify_contains": 'return "fixed"',
                    "verify_not_contains": 'return "broken"',
                    "verify_python_syntax": True,
                }
            ],
        }

    def _repair_plan(self) -> dict:
        return {
            "ok": True,
            "goal": "Repair edit fixes verification before evidence export",
            **self._route_metadata(),
            "steps": [
                {
                    "type": "controlled_edit",
                    "description": "repair attempt satisfies verifier",
                    "target_path": self.target_path,
                    "edit_payload": {
                        "schema": "replacement_pair_v1",
                        "old_text": 'return "broken"',
                        "new_text": 'return "fixed"',
                    },
                    "verify_contains": 'return "fixed"',
                    "verify_not_contains": 'return "broken"',
                    "verify_python_syntax": True,
                },
                {
                    "type": "command",
                    "description": "compile repaired workcopy file",
                    "command": f'"{sys.executable}" -m py_compile {self.target_path}',
                    "command_cwd": str(self.repo_root),
                },
            ],
        }


def test_migration_block_does_not_export_success_evidence(tmp_path: Path) -> None:
    result, _target, planner = _run_repaired_code_chain(tmp_path)

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["status"] == "migration_required"
    assert result["execution"]["executed"] is False
    assert result["execution"]["error"] == "legacy_runtime_dispatcher_migration_required"
    assert len(planner.calls) == 1
    assert "repair_result_evidence" not in result
    assert list_evidence(result["reviewable_result"]["task_id"], repo_root=tmp_path) == []


def test_migration_block_preserves_workcopy_without_repair_success(tmp_path: Path) -> None:
    result, target, _planner = _run_repaired_code_chain(tmp_path)

    assert target.read_text(encoding="utf-8") == 'def status():\n    return "broken"\n'
    assert result["ok"] is False
    assert result["execution"]["executed"] is False
    assert result.get("finished") is not True
    assert result.get("completed") is not True


def test_evidence_export_helper_is_reporting_only(tmp_path: Path) -> None:
    report = {
        "ok": True,
        "status": "ok",
        "attempt_count": 2,
        "original_failure": {"ok": False, "message": "first failure"},
        "repair_attempt_executed": True,
        "attempt_history": [
            {"attempt_index": 1, "attempt_kind": "initial", "ok": False},
            {"attempt_index": 2, "attempt_kind": "repair", "ok": True},
        ],
        "verification_history": [
            {"attempt_index": 1, "attempt_kind": "initial", "ok": False},
            {"attempt_index": 2, "attempt_kind": "repair", "ok": True},
        ],
    }

    evidence = export_code_chain_repair_evidence(
        repo_root=tmp_path,
        task_id="task with spaces",
        repair_result_report=report,
    )

    payload = json.loads(Path(evidence["artifact_path"]).read_text(encoding="utf-8"))
    indexed = list_evidence("task with spaces", repo_root=tmp_path)

    assert payload["original_failure"] == {"ok": False, "message": "first failure"}
    assert "task_with_spaces_repair_result_report.json" in evidence["artifact_path"]
    assert len(indexed) == 1
    assert indexed[0]["evidence_type"] == "code_chain_repair_report"
    assert indexed[0]["path"] == evidence["artifact_path"]


def test_no_scheduler_or_agent_loop_ownership_was_added() -> None:
    from core.agent import agent_loop
    from core.tasks import scheduler

    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "code_chain_repair_evidence" not in agent_loop_source
    assert "repair_result_report" not in agent_loop_source
    assert "code_chain_repair_evidence" not in scheduler_source
    assert "repair_result_report" not in scheduler_source


def test_no_second_repair_pipeline_or_executor_is_created() -> None:
    import core.agent.code_chain_controlled_self_edit_bridge as bridge
    import core.agent.code_chain_repair_evidence as evidence

    bridge_source = inspect.getsource(bridge)
    evidence_source = inspect.getsource(evidence)

    assert "class" not in evidence_source
    assert "StepExecutor" not in evidence_source
    assert "autonomous_repair_loop" not in bridge_source
    assert "RepairExecutor" not in bridge_source
    assert bridge_source.count("execute_code_chain_attempt(") == 3


def _run_repaired_code_chain(tmp_path: Path):
    repo_root = tmp_path
    workspace_root = repo_root / "workspace"
    target_path = "workspace/shared/workcopy/repair_evidence_target.py"
    target = repo_root / target_path
    target.parent.mkdir(parents=True)
    target.write_text('def status():\n    return "broken"\n', encoding="utf-8")

    planner = RepairEvidencePlanner(target_path=target_path, repo_root=repo_root)
    loop = AgentLoop(
        planner=planner,
        step_executor=StepExecutor(workspace_root=workspace_root),
        repo_root=str(repo_root),
        debug=False,
    )

    result = loop.run("fix the workcopy failure and export repair evidence")
    return result, target, planner
