from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_recovery_pipeline import (

    PIPELINE_STATUS_BLOCKED,
    PIPELINE_STATUS_READY_TO_CONTINUE,
    PIPELINE_STATUS_REVIEW_REQUIRED,
    RuntimeRecoveryPipeline,
    run_runtime_failure_recovery,
)
import pytest

pytestmark = [pytest.mark.integration]



def test_pipeline_turns_simple_failure_into_continuable_runtime_patch():
    result = run_runtime_failure_recovery(
        source_state={
            "session_id": "session-1",
            "status": "failed",
        },
        source_failure={
            "error": "tool_error",
        },
        metadata={
            "recovery_id": "recovery-1",
        },
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["final_status"] == PIPELINE_STATUS_READY_TO_CONTINUE
    assert payload["runtime_state_patch"]["status"] == "running"
    assert payload["runtime_state_patch"]["next_action"] == "resume_runtime"


def test_pipeline_blocks_unapproved_rollback_before_runtime_patch_resume():
    result = run_runtime_failure_recovery(
        source_state={
            "session_id": "session-rollback",
            "status": "failed",
            "rollback_required": True,
        },
        source_failure={
            "error": "mutation_failed",
            "rollback_required": True,
        },
        metadata={
            "recovery_id": "recovery-rollback",
        },
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["final_status"] == PIPELINE_STATUS_BLOCKED
    assert payload["runtime_state_patch"]["status"] == "blocked"
    assert payload["runtime_state_patch"]["recovery_requires_approval"] is True
    assert payload["runtime_state_patch"]["recovery_approved"] is False


def test_pipeline_routes_extended_mutation_to_waiting_review():
    result = run_runtime_failure_recovery(
        source_state={
            "session_id": "session-review",
            "status": "failed",
        },
        source_failure={
            "error": "extended_mutation",
        },
        metadata={
            "recovery_id": "recovery-review",
            "mutation_scope": "extended",
        },
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["final_status"] == PIPELINE_STATUS_REVIEW_REQUIRED
    assert payload["runtime_state_patch"]["status"] == "waiting_review"
    assert payload["runtime_state_patch"]["recovery_requires_approval"] is True


def test_pipeline_records_journal_entry_without_mutating_source_state():
    journal = RuntimeJournal()
    source_state = {
        "session_id": "session-journal",
        "status": "failed",
    }

    pipeline = RuntimeRecoveryPipeline(journal=journal)
    result = pipeline.run_failure_recovery(
        source_state=source_state,
        source_failure={"error": "failure"},
        metadata={"recovery_id": "recovery-journal"},
    )

    assert source_state["status"] == "failed"
    assert result.final_status == PIPELINE_STATUS_READY_TO_CONTINUE
    records = journal.replay_records()
    assert len(records) == 1
    assert records[0].record_type == "runtime_recovery_pipeline"


def test_pipeline_supports_custom_executor_payload():
    class Executor:
        def execute_recovery(self, chain, source_state, metadata):
            return {
                "recovery_id": chain["recovery_id"],
                "source_session_id": chain["source_session_id"],
                "status": "completed",
                "rollback_required": False,
                "rollback_executed": False,
                "custom_executor": True,
            }

    pipeline = RuntimeRecoveryPipeline(executor=Executor())
    result = pipeline.run_failure_recovery(
        source_state={
            "session_id": "session-custom",
            "status": "failed",
        },
        source_failure={"error": "custom"},
        metadata={"recovery_id": "recovery-custom"},
    )

    payload = result.to_dict()

    assert payload["execution"]["custom_executor"] is True
    assert payload["final_status"] == PIPELINE_STATUS_READY_TO_CONTINUE
