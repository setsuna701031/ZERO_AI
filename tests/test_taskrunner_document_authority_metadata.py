from __future__ import annotations

from core.runtime.task_runner import TaskRunner


def test_document_pipeline_shared_write_gets_closure_compatible_authority_metadata() -> None:
    runner = TaskRunner()

    task = {
        "task_id": "task_doc_authority_smoke",
        "task_type": "document",
        "planner_result": {
            "intent": "summary",
            "meta": {"semantic_type": "summary"},
        },
    }
    state = {"task_name": "task_doc_authority_smoke"}
    step = {
        "type": "write_file",
        "id": "step_write_summary",
        "path": "workspace/shared/summary.txt",
    }

    context = runner._build_taskrunner_authority_context(
        task=task,
        state=state,
        step=step,
        upstream_context={},
    )

    authority = context.get("execution_authority")

    assert context.get("execution_authority_granted") is True
    assert context.get("can_execute_privileged_step") is True
    assert authority["task_id"] == "task_doc_authority_smoke"
    assert authority["step_id"] == "step_write_summary"
    assert authority["authority_source"] == "operator_cli"
    assert authority["authority_status"] == "allowed"
    assert authority["execution_authority_endpoint"] == "step_executor"
    assert authority["action_type"] == "mutation"
    assert authority["approval_state"] == "approved"
    assert authority["approval_mode"] == "controlled_document_pipeline"
    assert authority["policy_result"]["allowed"] is True
    assert authority["trace_id"]


def test_non_document_write_does_not_get_bounded_authority_metadata() -> None:
    runner = TaskRunner()

    context = runner._build_taskrunner_authority_context(
        task={"task_id": "task_no_grant"},
        state={},
        step={
            "type": "write_file",
            "id": "step_write_core",
            "path": "core/runtime/unsafe.py",
        },
        upstream_context={},
    )

    assert context.get("execution_authority_granted") is False
    assert context.get("execution_authority") == {}
