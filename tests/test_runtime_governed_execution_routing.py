from __future__ import annotations

from core.runtime.snapshot_loader.execution_routing import (
    build_runtime_routing_summary,
    route_mutation_runtime,
    route_patch_apply,
    route_readonly_execution,
    route_unrestricted_shell,
)


def test_readonly_execution_is_allowed_by_default() -> None:
    decision = route_readonly_execution()

    assert decision["action"] == "readonly_execution"
    assert decision["allowed"] is True


def test_mutation_runtime_is_blocked_by_default() -> None:
    decision = route_mutation_runtime()

    assert decision["action"] == "mutation_runtime"
    assert decision["allowed"] is False


def test_patch_apply_is_blocked_by_default() -> None:
    decision = route_patch_apply()

    assert decision["action"] == "patch_apply"
    assert decision["allowed"] is False


def test_unrestricted_shell_is_blocked_by_default() -> None:
    decision = route_unrestricted_shell()

    assert decision["action"] == "unrestricted_shell"
    assert decision["allowed"] is False


def test_runtime_routing_summary_contract() -> None:
    summary = build_runtime_routing_summary()

    allowed_actions = summary["allowed_actions"]
    blocked_actions = summary["blocked_actions"]

    assert "readonly_execution" in allowed_actions

    assert "mutation_runtime" in blocked_actions
    assert "patch_apply" in blocked_actions
    assert "unrestricted_shell" in blocked_actions

    assert "unrestricted_shell" not in allowed_actions
    assert "mutation_runtime" not in allowed_actions
    assert "patch_apply" not in allowed_actions