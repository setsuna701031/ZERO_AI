from __future__ import annotations

from core.runtime.task_runner import TaskRunner
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_document_pipeline_shared_write_does_not_synthesize_authority_metadata() -> None:
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

    assert context.get("execution_authority_granted") is False
    assert context.get("can_execute_privileged_step") is False
    assert context.get("execution_authority") == {}
    assert context.get("authority_role") == "propagation"
    assert context.get("authority_policy") == "canonical_runtime_dispatch_capability_required"


def test_document_pipeline_shared_write_rejects_explicit_authority_without_live_capability() -> None:
    runner = TaskRunner()
    authority = {
        "task_id": "task_doc_authority_smoke",
        "step_id": "approved_demo_flow",
        "trace_id": "trace:doc",
        "runtime_session": "session:doc",
        "authority_source": "operator_cli",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "execute_or_mutation",
        "approval_state": "approved",
        "policy_result": {"allowed": True},
    }
    context = runner._build_taskrunner_authority_context(
        task={
            "task_id": "task_doc_authority_smoke",
            "task_type": "document",
            "execution_authority": authority,
            "authority_propagation_required": True,
        },
        state={},
        step={"type": "write_file", "path": "workspace/shared/summary.txt"},
        upstream_context={},
    )

    assert context["execution_authority"] == {}
    assert context["authority_role"] == "propagation"
    assert context["authority_policy"] == "canonical_runtime_dispatch_capability_required"
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is False


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
    assert context.get("can_execute_privileged_step") is False
    assert context.get("execution_authority") == {}
    assert context.get("authority_role") == "propagation"
