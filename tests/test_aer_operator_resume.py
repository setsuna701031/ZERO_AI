from __future__ import annotations

import inspect

from core.runtime.aer_operator_checkpoint import (
    build_operator_checkpoint,
    compute_checkpoint_integrity_hash,
)
from core.runtime.aer_operator_checkpoint_store import save_checkpoint
from core.runtime.aer_operator_resume import (
    AER_OPERATOR_RESUME_CONTRACT,
    build_resume_result,
    resume_from_checkpoint,
    resume_from_payload,
    validate_resume_result,
)
import core.runtime.aer_operator_resume as resume_module


def test_resume_from_payload_composes_checkpoint_context_and_state_machine() -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="checkpointed",
        completed_phases=("initialized", "admitted", "running"),
        pending_phases=("resumed",),
        resume_token="resume-token-1",
        metadata={"note": "ready"},
    )

    result = resume_from_payload(checkpoint)

    assert result["ok"] is True
    assert result["contract"] == AER_OPERATOR_RESUME_CONTRACT
    assert result["checkpoint"] == checkpoint
    assert result["checkpoint_id"] == "checkpoint-1"
    assert result["execution_context"]["operator_session_id"] == "operator-session-1"
    assert result["execution_context"]["package_id"] == "package-84"
    assert result["execution_context"]["checkpoint_id"] == "checkpoint-1"
    assert result["execution_context"]["current_phase"] == "resumed"
    assert result["lifecycle_phase"] == "resumed"
    assert result["transition_result"]["ok"] is True
    assert result["transition_result"]["transition"]["from_phase"] == "checkpointed"
    assert result["transition_result"]["transition"]["to_phase"] == "resumed"
    assert result["metadata"]["resume_token"] == "resume-token-1"
    assert validate_resume_result(result)["ok"] is True


def test_resume_from_checkpoint_loads_only_through_store(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="checkpointed",
    )
    save_checkpoint(str(tmp_path), checkpoint)

    result = resume_from_checkpoint(str(tmp_path), "checkpoint-1")

    assert result["ok"] is True
    assert result["checkpoint"] == checkpoint
    assert result["execution_context"]["current_phase"] == "resumed"


def test_resume_from_checkpoint_returns_structured_error_for_missing_checkpoint(tmp_path) -> None:
    result = resume_from_checkpoint(str(tmp_path), "missing")

    assert result["ok"] is False
    assert "checkpoint not found" in result["errors"]
    assert validate_resume_result(result)["ok"] is True


def test_resume_from_payload_returns_structured_error_for_invalid_checkpoint() -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="checkpointed",
    )
    checkpoint["package_id"] = ""

    result = resume_from_payload(checkpoint)

    assert result["ok"] is False
    assert "package_id is required" in result["errors"]
    assert validate_resume_result(result)["ok"] is True


def test_resume_from_payload_surfaces_state_machine_transition_errors() -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="completed",
    )

    result = resume_from_payload(checkpoint)

    assert result["ok"] is False
    assert result["lifecycle_phase"] == "completed"
    assert "transition not allowed: completed -> resumed" in result["errors"]
    assert result["transition_result"]["transition"]["from_phase"] == "completed"
    assert result["transition_result"]["transition"]["to_phase"] == "resumed"


def test_build_resume_result_returns_deep_copies() -> None:
    checkpoint = {"checkpoint_id": "checkpoint-1", "metadata": {"nested": "original"}}
    context = {"metadata": {"nested": "original"}}

    result = build_resume_result(
        ok=True,
        checkpoint_id="checkpoint-1",
        checkpoint=checkpoint,
        execution_context=context,
    )
    result["checkpoint"]["metadata"]["nested"] = "mutated"
    result["execution_context"]["metadata"]["nested"] = "mutated"

    assert checkpoint["metadata"]["nested"] == "original"
    assert context["metadata"]["nested"] == "original"


def test_validate_resume_result_rejects_invalid_shapes() -> None:
    assert "payload must be a dict" in validate_resume_result(None)["errors"]

    result = build_resume_result(ok=True, checkpoint_id="checkpoint-1")
    result["contract"] = "wrong.contract"
    result["errors"] = ["unexpected"]
    result["metadata"] = []

    validation = validate_resume_result(result)

    assert validation["ok"] is False
    assert "invalid contract" in validation["errors"]
    assert "metadata must be a dict" in validation["errors"]
    assert "successful resume result must not include errors" in validation["errors"]


def test_resume_module_does_not_use_direct_persistence_primitives() -> None:
    source = inspect.getsource(resume_module)

    forbidden = (
        "open(",
        "json.load",
        "json.dump",
        "os.replace",
        "Path.write_text",
        "save_checkpoint",
        "delete_checkpoint",
    )
    for token in forbidden:
        assert token not in source


def test_resume_from_payload_rejects_checkpoint_integrity_mismatch() -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="checkpointed",
    )
    checkpoint["phase"] = "running"

    result = resume_from_payload(checkpoint)

    assert result["ok"] is False
    assert "integrity_hash mismatch" in result["errors"]


def test_resume_from_payload_uses_checkpoint_model_validation_not_local_hash_logic() -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-84",
        phase="checkpointed",
    )
    checkpoint["phase"] = "running"
    checkpoint["integrity_hash"] = compute_checkpoint_integrity_hash(checkpoint)

    result = resume_from_payload(checkpoint)

    assert result["ok"] is False
    assert "transition not allowed: running -> resumed" in result["errors"]
