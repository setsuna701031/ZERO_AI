from __future__ import annotations

from core.runtime.snapshot_loader.controlled_execution_bridge import (
    build_controlled_execution_bridge_summary,
    route_controlled_execution,
)


def test_controlled_execution_allows_readonly_without_handler() -> None:
    result = route_controlled_execution(
        "readonly_execution",
        payload={"task": "inspect"},
    )

    assert result["ok"] is True
    assert result["status"] == "allowed_no_handler"
    assert result["action"] == "readonly_execution"
    assert result["decision"]["allowed"] is True
    assert result["payload"] == {"task": "inspect"}


def test_controlled_execution_runs_readonly_handler_when_allowed() -> None:
    result = route_controlled_execution(
        "readonly_execution",
        payload={"value": 7},
        handlers={
            "readonly_execution": lambda payload: {
                "observed": payload["value"],
                "mode": "readonly",
            }
        },
    )

    assert result["ok"] is True
    assert result["status"] == "executed"
    assert result["action"] == "readonly_execution"
    assert result["result"] == {"observed": 7, "mode": "readonly"}


def test_controlled_execution_blocks_mutation_runtime() -> None:
    result = route_controlled_execution(
        "mutation_runtime",
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
    assert result["decision"]["allowed"] is False


def test_controlled_execution_blocks_patch_apply() -> None:
    result = route_controlled_execution(
        "patch_apply",
        payload={"patch": "diff --git ..."},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "patch_apply"
    assert result["decision"]["allowed"] is False


def test_controlled_execution_blocks_unrestricted_shell() -> None:
    result = route_controlled_execution(
        "unrestricted_shell",
        payload={"command": "dir"},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "unrestricted_shell"
    assert result["decision"]["allowed"] is False


def test_controlled_execution_blocks_unknown_action() -> None:
    result = route_controlled_execution(
        "dangerous_unknown_action",
        payload={"x": 1},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "dangerous_unknown_action"
    assert result["decision"]["allowed"] is False
    assert result["reason"] == "unknown_runtime_action"


def test_controlled_execution_bridge_summary_contract() -> None:
    summary = build_controlled_execution_bridge_summary()

    assert summary["bridge"] == "controlled_execution_bridge"
    assert "readonly_execution" in summary["allowed_actions"]
    assert "mutation_runtime" in summary["blocked_actions"]
    assert "patch_apply" in summary["blocked_actions"]
    assert "unrestricted_shell" in summary["blocked_actions"]
    assert "unrestricted_shell" not in summary["allowed_actions"]