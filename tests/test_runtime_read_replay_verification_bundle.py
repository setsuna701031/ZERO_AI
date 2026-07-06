from __future__ import annotations

from core.runtime.runtime_read_replay_verification import (
    build_runtime_read_replay_verification_audit_record,
    build_runtime_read_replay_verification_milestone_seal,
    build_runtime_read_replay_verification_record,
    build_runtime_read_replay_verification_request,
    validate_runtime_read_replay_verification_request,
)


def _digest():
    return "a" * 64


def _evidence(**overrides):
    evidence = {
        "read_execution_id": "read-execution::read-adapter::README.md::read-execution-1265",
        "execution_status": "succeeded",
        "content_digest": _digest(),
        "content_metadata": {
            "content_length": 128,
            "resource_reference": "README.md",
            "content_included": False,
            "immutable": True,
            "expired": False,
        },
        "immutable_record": True,
        "evidence_ownership": {
            "evidence_owner": "runtime_controlled_read_execution",
            "owner_session_id": "limited-runtime-session::birth-1209",
        },
    }
    evidence.update(overrides)
    return evidence


def _request(**overrides):
    request = build_runtime_read_replay_verification_request(
        replay_verification_request_id="read-replay-1273",
        read_evidence=_evidence(),
        current_digest=_digest(),
        verification_timestamp="deterministic-tick-1273",
    )
    request.update(overrides)
    return request


def test_1273_missing_read_evidence_fails():
    validation = validate_runtime_read_replay_verification_request(
        _request(read_evidence={})
    )
    record = build_runtime_read_replay_verification_record(_request(read_evidence={}))

    assert validation["valid"] is False
    assert record["verification_status"] == "invalid"
    assert "missing_read_evidence" in record["mismatch_reason"]


def test_1274_invalid_read_execution_fails():
    request = _request(read_evidence=_evidence(execution_status="failed"))

    validation = validate_runtime_read_replay_verification_request(request)
    record = build_runtime_read_replay_verification_record(request)

    assert validation["valid"] is False
    assert record["verification_status"] == "invalid"
    assert "invalid_read_execution" in record["mismatch_reason"]


def test_1275_matching_digest_verifies():
    record = build_runtime_read_replay_verification_record(_request())
    validation = validate_runtime_read_replay_verification_request(_request())

    assert validation["valid"] is True
    assert record["verification_status"] == "verified"
    assert record["original_digest"] == _digest()
    assert record["current_digest"] == _digest()
    assert record["mismatch_reason"] == "none"
    assert record["mutation_readiness_allowed"] is True


def test_1276_changed_digest_creates_mismatch():
    request = _request(current_digest="b" * 64)
    record = build_runtime_read_replay_verification_record(request)

    assert record["verification_status"] == "mismatch"
    assert record["mismatch_reason"] == "content_digest_changed"
    assert record["stale_read_detected"] is True


def test_1276_mismatch_blocks_mutation_readiness():
    request = _request(current_digest="b" * 64)
    validation = validate_runtime_read_replay_verification_request(request)
    record = build_runtime_read_replay_verification_record(request)

    assert validation["mutation_readiness_allowed"] is False
    assert record["mutation_readiness_allowed"] is False


def test_1277_expired_evidence_fails():
    metadata = _evidence()["content_metadata"]
    metadata["expired"] = True
    request = _request(read_evidence=_evidence(content_metadata=metadata))
    record = build_runtime_read_replay_verification_record(request)

    assert record["verification_status"] == "expired"
    assert "read_evidence_expired" in record["mismatch_reason"]


def test_1278_replay_does_not_read_unauthorized_resource():
    record = build_runtime_read_replay_verification_record(_request())
    audit = build_runtime_read_replay_verification_audit_record(_request())

    assert record["resource_read_performed"] is False
    assert audit["resource_read_performed"] is False


def test_1278_replay_cannot_write():
    record = build_runtime_read_replay_verification_record(_request())

    assert record["write_performed"] is False
    assert record["network_performed"] is False


def test_1279_replay_cannot_mutate():
    record = build_runtime_read_replay_verification_record(_request())

    assert record["mutation_performed"] is False
    assert record["executor_action_performed"] is False
    assert record["autonomy_started"] is False
    assert record["background_loop_started"] is False


def test_1280_replay_cannot_execute_and_audit_seal():
    record = build_runtime_read_replay_verification_record(_request())
    audit = build_runtime_read_replay_verification_audit_record(_request())
    seal = build_runtime_read_replay_verification_milestone_seal(_request())

    assert record["subprocess_started"] is False
    assert record["shell_started"] is False
    assert audit["decision"] == "reserved_runtime_read_replay_verification_only"
    assert audit["subprocess_started"] is False
    assert audit["shell_started"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1281
    assert seal["all_effect_surfaces_locked"] is True
