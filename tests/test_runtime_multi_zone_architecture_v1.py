from core.runtime.runtime_multi_zone_architecture import (
    ROUTE_ALLOWED,
    ROUTE_BLOCKED,
    ROUTE_REDIRECTED,
    ZONE_MUTATION,
    ZONE_REPAIR,
    ZONE_SANDBOX,
    RuntimeMultiZoneArchitecture,
)


def test_multi_zone_routes_repair_steps():
    runtime = RuntimeMultiZoneArchitecture()

    result = runtime.route_step(
        step={
            "type": "repair",
        }
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["selected_zone"] == ZONE_REPAIR
    assert payload["route_status"] == ROUTE_ALLOWED


def test_multi_zone_routes_mutation_steps():
    runtime = RuntimeMultiZoneArchitecture()

    result = runtime.route_step(
        step={
            "type": "mutation",
        }
    )

    assert result.selected_zone == ZONE_MUTATION
    assert result.execution_allowed is True


def test_multi_zone_redirects_unknown_steps_to_sandbox():
    runtime = RuntimeMultiZoneArchitecture()

    result = runtime.route_step(
        step={
            "type": "experimental_unknown",
        }
    )

    assert result.selected_zone == ZONE_SANDBOX
    assert result.route_status == ROUTE_REDIRECTED


def test_multi_zone_blocks_isolated_zone():
    runtime = RuntimeMultiZoneArchitecture()

    runtime.isolate_zone(ZONE_MUTATION)

    result = runtime.route_step(
        step={
            "type": "mutation",
        }
    )

    assert result.route_status == ROUTE_BLOCKED
    assert result.execution_allowed is False


def test_multi_zone_preserves_zone_topology():
    runtime = RuntimeMultiZoneArchitecture()

    result = runtime.route_step(
        step={
            "type": "repair",
        }
    )

    assert len(result.runtime_zones) >= 5
