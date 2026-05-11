from __future__ import annotations

from core.tasks.planner_gateway import (
    build_noop_planner_payload,
    call_planner_gateway,
    export_scheduler_planner_payload,
)


class GatewayObjectPlanner:
    def plan(self, request):
        return {
            "action": "write_file",
            "target_path": request["target_path"],
            "content": request["content"],
            "goal": request["goal"],
        }


class GatewayBrokenPlanner:
    def plan(self, request):
        raise RuntimeError("gateway boom")


def test_gateway_accepts_object_planner():
    result = call_planner_gateway(
        GatewayObjectPlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert result.ok is True
    assert result.gateway_error is None
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["content"] == "hello"
    assert result.payload["planner_gateway_ok"] is True
    assert result.payload["planner_gateway_errors"] == []


def test_gateway_accepts_callable_planner():
    def planner(request):
        return {
            "payload": {
                "action": "verify_file",
                "target_path": request["target_path"],
                "goal": "verify output",
            }
        }

    result = call_planner_gateway(
        planner,
        {"target_path": "workspace/shared/out.txt"},
    )

    assert result.ok is True
    assert result.payload["action"] == "verify_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["planner_gateway_ok"] is True


def test_gateway_exports_scheduler_payload_only():
    payload = export_scheduler_planner_payload(
        GatewayObjectPlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert payload["action"] == "write_file"
    assert payload["planner_gateway_ok"] is True
    assert payload["runtime_entry_ok"] is True
    assert payload["adapter_ok"] is True


def test_gateway_blocks_invalid_payload():
    def planner(request):
        return {
            "action": "write_file",
            "content": "missing path",
        }

    result = call_planner_gateway(planner, {})

    assert result.ok is False
    assert result.payload["action"] == "write_file"
    assert result.payload["planner_gateway_ok"] is False
    assert "write_file:missing_target_path" in result.errors
    assert "write_file:missing_target_path" in result.payload["planner_gateway_errors"]


def test_gateway_handles_planner_exception_as_noop():
    result = call_planner_gateway(GatewayBrokenPlanner(), {})

    assert result.ok is False
    assert result.payload["action"] == "noop"
    assert result.payload["planner_gateway_ok"] is False
    assert result.gateway_error is not None
    assert result.gateway_error.startswith("planner_invocation_failed:RuntimeError:gateway boom")


def test_build_noop_planner_payload_is_scheduler_safe():
    payload = build_noop_planner_payload(
        reason="manual fallback",
        goal="safe fallback",
    )

    assert payload["action"] == "noop"
    assert payload["goal"] == "safe fallback"
    assert payload["reason"] == "manual fallback"
    assert payload["planner_gateway_ok"] is True
    assert payload["runtime_entry_invoked"] is False
    assert payload["contract_errors"] == []