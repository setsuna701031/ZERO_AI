from __future__ import annotations

from core.planning.planner_runtime_entry import (
    export_planner_runtime_payload,
    run_planner_runtime_entry,
)


class ObjectPlanner:
    def plan(self, request):
        return {
            "action": "write_file",
            "target_path": request["target_path"],
            "content": request["content"],
            "goal": request["goal"],
        }


class CustomMethodPlanner:
    def make_plan(self, request):
        return {
            "payload": {
                "action": "verify_file",
                "target_path": request["target_path"],
                "goal": "verify via custom method",
            }
        }


class BrokenPlanner:
    def plan(self, request):
        raise RuntimeError("boom")


def test_runtime_entry_invokes_callable_planner():
    def planner(request):
        return {
            "action": "append",
            "filename": request["target_path"],
            "body": "line",
        }

    result = run_planner_runtime_entry(
        planner,
        {"target_path": "workspace/shared/log.txt"},
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.invocation_error is None
    assert result.payload["action"] == "append_file"
    assert result.payload["target_path"] == "workspace/shared/log.txt"
    assert result.payload["content"] == "line"
    assert result.payload["runtime_entry_ok"] is True
    assert result.payload["runtime_entry_invoked"] is True


def test_runtime_entry_invokes_object_plan_method():
    result = run_planner_runtime_entry(
        ObjectPlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert result.ok is True
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["content"] == "hello"


def test_runtime_entry_invokes_custom_method_name():
    result = run_planner_runtime_entry(
        CustomMethodPlanner(),
        {"target_path": "workspace/shared/out.txt"},
        method_name="make_plan",
    )

    assert result.ok is True
    assert result.payload["action"] == "verify_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"


def test_runtime_entry_exports_payload_only():
    payload = export_planner_runtime_payload(
        ObjectPlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert payload["action"] == "write_file"
    assert payload["runtime_entry_ok"] is True
    assert payload["runtime_entry_invoked"] is True


def test_runtime_entry_blocks_invalid_planner_result():
    def planner(request):
        return {
            "action": "write_file",
            "content": "missing path",
        }

    result = run_planner_runtime_entry(planner, {})

    assert result.ok is False
    assert result.invoked is True
    assert result.payload["action"] == "write_file"
    assert "write_file:missing_target_path" in result.errors
    assert result.payload["runtime_entry_ok"] is False


def test_runtime_entry_handles_planner_exception_as_noop():
    result = run_planner_runtime_entry(BrokenPlanner(), {})

    assert result.ok is False
    assert result.invoked is False
    assert result.payload["action"] == "noop"
    assert result.payload["runtime_entry_ok"] is False
    assert result.payload["runtime_entry_invoked"] is False
    assert result.invocation_error is not None
    assert result.invocation_error.startswith("planner_invocation_failed:RuntimeError:boom")


def test_runtime_entry_handles_missing_planner_method_as_noop():
    result = run_planner_runtime_entry(
        object(),
        {},
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.payload["action"] == "noop"
    assert result.payload["runtime_entry_ok"] is False
    assert result.invocation_error is not None
    assert "planner_invocation_failed:AttributeError" in result.invocation_error