from core.runtime.governed_runtime_continuation_session import (
    SESSION_CONTINUED,
    SESSION_SUSPENDED,
    build_governed_runtime_continuation_record,
    validate_governed_runtime_continuation_record,
)


def test_builds_continuation_record():
    record = build_governed_runtime_continuation_record(
        source_session_id="session-a",
        replay_session_id="replay-a",
    )

    assert record["source_session_id"] == "session-a"
    assert record["replay_session_id"] == "replay-a"
    assert record["continuation_state"] == SESSION_CONTINUED
    assert record["data_only"] is True
    assert len(record["lineage_chain"]) == 3


def test_validates_continuation_record():
    record = build_governed_runtime_continuation_record(
        source_session_id="session-a",
        replay_session_id="replay-a",
    )

    validation = validate_governed_runtime_continuation_record(record)

    assert validation["continuation_valid"] is True
    assert validation["continuation_state"] == SESSION_CONTINUED
    assert validation["issues"] == []


def test_blocks_invalid_lineage():
    record = build_governed_runtime_continuation_record(
        source_session_id="session-a",
        replay_session_id="replay-a",
    )

    record["lineage_chain"] = ["session-a"]

    validation = validate_governed_runtime_continuation_record(record)

    assert validation["continuation_valid"] is False
    assert validation["continuation_state"] == SESSION_SUSPENDED
    assert "lineage_incomplete" in validation["issues"]
