from core.runtime.runtime_zone_communication_governance import (
    BRIDGE_AUTHORITY,
    BRIDGE_GOVERNED,
    BRIDGE_READ_ONLY,
    CHANNEL_BLOCKED,
    CHANNEL_BRIDGED,
    CHANNEL_REVIEW_REQUIRED,
    ZONE_AUTHORITY,
    ZONE_MAIN,
    ZONE_MUTATION,
    ZONE_REPAIR,
    ZONE_REPLAY,
    ZONE_SANDBOX,
    govern_zone_message,
)


def test_authority_can_bridge_to_main_runtime():
    result = govern_zone_message(
        source_zone=ZONE_AUTHORITY,
        target_zone=ZONE_MAIN,
        message_type="apply_runtime_transition",
        payload={"status": "running"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["channel_status"] == CHANNEL_BRIDGED
    assert payload["bridge"] == BRIDGE_AUTHORITY
    assert payload["allowed"] is True


def test_mutation_cannot_directly_write_main_runtime():
    result = govern_zone_message(
        source_zone=ZONE_MUTATION,
        target_zone=ZONE_MAIN,
        message_type="write_state",
        payload={"status": "running"},
    )

    assert result.channel_status == CHANNEL_REVIEW_REQUIRED
    assert result.allowed is False
    assert result.bridge == BRIDGE_GOVERNED


def test_sandbox_cannot_contact_authority():
    result = govern_zone_message(
        source_zone=ZONE_SANDBOX,
        target_zone=ZONE_AUTHORITY,
        message_type="apply_patch",
        payload={},
    )

    assert result.channel_status == CHANNEL_BLOCKED
    assert result.allowed is False


def test_replay_can_send_read_only_reference_to_main():
    result = govern_zone_message(
        source_zone=ZONE_REPLAY,
        target_zone=ZONE_MAIN,
        message_type="replay_reference",
        payload={"replay_id": "replay-1"},
    )

    assert result.channel_status == CHANNEL_BRIDGED
    assert result.bridge == BRIDGE_READ_ONLY
    assert result.allowed is True


def test_repair_runtime_uses_governed_bridge():
    result = govern_zone_message(
        source_zone=ZONE_REPAIR,
        target_zone=ZONE_AUTHORITY,
        message_type="recovery_request",
        payload={"recovery_id": "recovery-1"},
    )

    assert result.channel_status == CHANNEL_BRIDGED
    assert result.bridge == BRIDGE_GOVERNED
    assert result.allowed is True
