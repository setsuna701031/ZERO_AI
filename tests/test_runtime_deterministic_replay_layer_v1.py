from core.runtime.runtime_deterministic_replay_layer import (
    DETERMINISTIC_REPLAY_BLOCKED,
    DETERMINISTIC_REPLAY_DIVERGED,
    DETERMINISTIC_REPLAY_VERIFIED,
    DIVERGENCE_EVENT_COUNT_MISMATCH,
    DIVERGENCE_HASH_MISMATCH,
    DIVERGENCE_NONE,
    RuntimeDeterministicReplayLayer,
    verify_deterministic_runtime_replay,
)


def _events():
    return [
        {
            "event_type": "execution_event",
            "runtime_zone": "main_runtime",
            "payload": {"status": "running"},
            "sequence": 1,
        },
        {
            "event_type": "recovery_event",
            "runtime_zone": "repair_runtime",
            "payload": {"recovery": "started"},
            "sequence": 2,
        },
    ]


def test_deterministic_replay_verifies_identical_event_stream():
    events = _events()

    decision = verify_deterministic_runtime_replay(
        baseline_events=events,
        replay_events=list(reversed(events)),
    )

    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["replay_status"] == DETERMINISTIC_REPLAY_VERIFIED
    assert payload["deterministic"] is True
    assert payload["divergence_type"] == DIVERGENCE_NONE


def test_deterministic_replay_detects_payload_divergence():
    baseline = _events()
    replay = _events()
    replay[1]["payload"] = {"recovery": "changed"}

    decision = verify_deterministic_runtime_replay(
        baseline_events=baseline,
        replay_events=replay,
    )

    assert decision.replay_status == DETERMINISTIC_REPLAY_DIVERGED
    assert decision.deterministic is False
    assert decision.divergence_type == DIVERGENCE_HASH_MISMATCH


def test_deterministic_replay_detects_event_count_mismatch():
    baseline = _events()
    replay = _events()[:1]

    decision = verify_deterministic_runtime_replay(
        baseline_events=baseline,
        replay_events=replay,
    )

    assert decision.replay_status == DETERMINISTIC_REPLAY_DIVERGED
    assert decision.divergence_type == DIVERGENCE_EVENT_COUNT_MISMATCH


def test_deterministic_replay_blocks_empty_stream():
    decision = verify_deterministic_runtime_replay(
        baseline_events=[],
        replay_events=[],
    )

    assert decision.replay_status == DETERMINISTIC_REPLAY_BLOCKED
    assert decision.deterministic is False


def test_deterministic_replay_trace_has_final_state_hash():
    runtime = RuntimeDeterministicReplayLayer()

    trace = runtime.build_trace(events=_events())

    assert trace.event_count == 2
    assert trace.canonical_hash
    assert trace.final_state_hash
    assert trace.final_state["event_count"] == 2
