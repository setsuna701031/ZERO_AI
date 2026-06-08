from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_app_legacy() -> Any:
    path = Path(__file__).resolve().parents[1] / "app_legacy.py"
    spec = importlib.util.spec_from_file_location("zero_app_legacy_demo_authority_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_document_pipeline_identity_authority_continuity() -> None:
    app = _load_app_legacy()
    authority = app._demo_execution_authority_for_task(
        {
            "task_id": "doc-identity",
            "task_type": "document",
            "scenario": "doc_summary",
            "outputs": ["workspace/shared/summary.txt"],
        },
        "doc-identity",
    )
    assert authority["authority_source"] == "operator_cli"
    assert authority["approval_mode"] == "controlled_document_pipeline"
    assert authority["action_type"] == "execute_or_mutation"


def test_requirement_demo_authority_continuity() -> None:
    app = _load_app_legacy()
    authority = app._demo_execution_authority_for_task(
        {"task_id": "requirement-demo", "task_type": "document", "scenario": "doc_requirement"},
        "requirement-demo",
    )
    assert authority["authority_status"] == "allowed"
    assert authority["execution_authority_endpoint"] == "step_executor"


def test_semantic_report_document_authority_continuity() -> None:
    app = _load_app_legacy()
    authority = app._demo_execution_authority_for_task(
        {"task_id": "semantic-report", "planner_result": {"intent": "report"}},
        "semantic-report",
    )
    assert authority["approval_mode"] == "controlled_document_pipeline"
    assert authority["authority_status"] == "allowed"


def test_execution_demo_authority_continuity() -> None:
    app = _load_app_legacy()
    authority = app._demo_execution_authority_for_task(
        {"task_id": "execution-demo", "scenario": "execution_proof"},
        "execution-demo",
    )
    assert authority["approval_mode"] == "controlled_execution_demo"
    assert authority["policy_result"]["allowed"] is True


def test_ordinary_task_does_not_receive_demo_authority() -> None:
    app = _load_app_legacy()
    assert app._demo_execution_authority_for_task(
        {"task_id": "ordinary", "task_type": "engineering_task"},
        "ordinary",
    ) == {}


def test_result_history_survives_scheduler_authority_fallback(tmp_path: Path) -> None:
    from core.tasks.scheduler_core.runtime_overlay_helpers import _direct_step_success_payload

    class Scheduler:
        current_tick = 7
        task_runtime = None

        def _persist_task_payload(self, task_id: str, task: dict[str, Any]) -> None:
            self.persisted = task

    scheduler = Scheduler()
    task = {
        "task_id": "history",
        "results": [{"step_index": 0, "result": {"text": "previous"}}],
        "execution_log": [{"step_index": 0, "result": {"text": "previous"}}],
    }
    result = _direct_step_success_payload(
        scheduler,
        task,
        [{"type": "write_file"}],
        0,
        {"ok": True, "message": "current"},
    )
    assert len(result["results"]) == 2
    assert result["results"][0]["result"]["text"] == "previous"
    assert len(result["execution_log"]) == 2
