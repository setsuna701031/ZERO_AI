from core.runtime.runtime_transaction_bus import (
    BUS_BLOCKED,
    BUS_ROUTED,
    CHANNEL_AUTHORITY,
    CHANNEL_MUTATION,
    CHANNEL_REPAIR,
    CHANNEL_REPLAY,
    ROUTE_ALLOWED,
    ROUTE_BLOCKED,
    ROUTE_REVIEW,
    ZONE_AUTHORITY,
    ZONE_MAIN,
    ZONE_MUTATION,
    ZONE_REPAIR,
    ZONE_REPLAY,
    RuntimeTransactionBus,
)


def test_repair_transaction_routes_successfully():
    runtime = RuntimeTransactionBus()

    result = runtime.submit_transaction(
        source_zone=ZONE_REPAIR,
        target_zone=ZONE_AUTHORITY,
        channel=CHANNEL_REPAIR,
        payload={"recovery_id": "recovery-1"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["route_status"] == ROUTE_ALLOWED
    assert payload["transaction"]["status"] == BUS_ROUTED


def test_mutation_transaction_requires_review():
    runtime = RuntimeTransactionBus()

    result = runtime.submit_transaction(
        source_zone=ZONE_MUTATION,
        target_zone=ZONE_MAIN,
        channel=CHANNEL_MUTATION,
        payload={"patch": "unsafe"},
    )

    assert result.route_status == ROUTE_REVIEW
    assert result.allowed is False
    assert result.transaction["status"] == BUS_BLOCKED


def test_replay_transaction_is_allowed():
    runtime = RuntimeTransactionBus()

    result = runtime.submit_transaction(
        source_zone=ZONE_REPLAY,
        target_zone=ZONE_MAIN,
        channel=CHANNEL_REPLAY,
        payload={"replay_id": "replay-1"},
    )

    assert result.route_status == ROUTE_ALLOWED
    assert result.transaction["status"] == BUS_ROUTED


def test_authority_escalation_is_allowed():
    runtime = RuntimeTransactionBus()

    result = runtime.submit_transaction(
        source_zone=ZONE_MAIN,
        target_zone=ZONE_AUTHORITY,
        channel=CHANNEL_AUTHORITY,
        payload={"incident": "runtime_failure"},
    )

    assert result.route_status == ROUTE_ALLOWED
    assert result.allowed is True


def test_unknown_transaction_route_is_blocked():
    runtime = RuntimeTransactionBus()

    result = runtime.submit_transaction(
        source_zone="unknown_zone",
        target_zone=ZONE_MAIN,
        channel="unsafe_channel",
        payload={},
    )

    assert result.route_status == ROUTE_BLOCKED
    assert result.transaction["status"] == BUS_BLOCKED
