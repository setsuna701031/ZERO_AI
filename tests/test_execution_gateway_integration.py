from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.execution_gateway_integration import (

    build_execution_gateway_integration_summary,
    build_gateway_request,
    execute_gateway_action,
    execute_gateway_request,
)
pytestmark = [pytest.mark.integration]



def test_build_gateway_request_contract() -> None:
    request = build_gateway_request(
        action="readonly_execution",
        payload={"task": "inspect"},
        source="test_gateway",
    )

    assert request == {
        "source": "test_gateway",
        "action": "readonly_execution",
        "payload": {"task": "inspect"},
    }


def test_build_gateway_request_rejects_empty_action() -> None:
    with pytest.raises(ValueError):
        build_gateway_request(action="   ")


def test_execute_gateway_action_allows_readonly_without_handler() -> None:
    result = execute_gateway_action(
        action="readonly_execution",
        payload={"task": "inspect"},
        source="test_gateway",
    )

    assert result["ok"] is True
    assert result["status"] == "allowed_no_handler"
    assert result["source"] == "test_gateway"
    assert result["action"] == "readonly_execution"
    assert result["gateway"] == "snapshot_loader_execution_gateway"
    assert result["bridge_result"]["decision"]["allowed"] is True


def test_execute_gateway_action_runs_readonly_handler_when_allowed() -> None:
    result = execute_gateway_action(
        action="readonly_execution",
        payload={"value": 11},
        handlers={
            "readonly_execution": lambda payload: {
                "observed": payload["value"],
                "mode": "gateway_readonly",
            }
        },
        source="test_gateway",
    )

    assert result["ok"] is True
    assert result["status"] == "executed"
    assert result["bridge_result"]["result"] == {
        "observed": 11,
        "mode": "gateway_readonly",
    }


def test_execute_gateway_action_blocks_mutation_runtime() -> None:
    result = execute_gateway_action(
        action="mutation_runtime",
        payload={"target": "core/runtime/example.py"},
        handlers={
            "mutation_runtime": lambda payload: {
                "should_not_run": True,
            }
        },
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "mutation_runtime"
    assert result["bridge_result"]["decision"]["allowed"] is False


def test_execute_gateway_action_blocks_patch_apply() -> None:
    result = execute_gateway_action(
        action="patch_apply",
        payload={"patch": "diff --git ..."},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "patch_apply"
    assert result["bridge_result"]["decision"]["allowed"] is False


def test_execute_gateway_action_blocks_unrestricted_shell() -> None:
    result = execute_gateway_action(
        action="unrestricted_shell",
        payload={"command": "dir"},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "unrestricted_shell"
    assert result["bridge_result"]["decision"]["allowed"] is False


def test_execute_gateway_request_rejects_bad_payload() -> None:
    with pytest.raises(TypeError):
        execute_gateway_request(
            {
                "source": "test_gateway",
                "action": "readonly_execution",
                "payload": ["not", "mapping"],
            }
        )


def test_execution_gateway_integration_summary_contract() -> None:
    summary = build_execution_gateway_integration_summary()

    assert summary["gateway"] == "snapshot_loader_execution_gateway"
    assert summary["bridge"] == "controlled_execution_bridge"
    assert "readonly_execution" in summary["allowed_actions"]
    assert "mutation_runtime" in summary["blocked_actions"]
    assert "patch_apply" in summary["blocked_actions"]
    assert "unrestricted_shell" in summary["blocked_actions"]
    assert "unrestricted_shell" not in summary["allowed_actions"]