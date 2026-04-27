from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.step_handlers import ToolStepHandler


class FakeToolRegistry:
    def __init__(self, result: Any) -> None:
        self.result = result

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        return self.result


class FakeExecutor:
    def __init__(self, result: Any) -> None:
        self.tool_registry = FakeToolRegistry(result)

    def _extract_inner_ok(self, result: Any) -> bool:
        if isinstance(result, dict):
            return bool(result.get("ok", True))
        return bool(result)


def fail(message: str) -> int:
    print(f"[step-handler-tool-result-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[step-handler-tool-result-smoke] PASS: {message}")


def run_case(
    name: str,
    tool_result: Any,
    *,
    expected_ok: bool,
    expected_error_type: str | None,
    expected_retryable: bool = False,
) -> int:
    print(f"[step-handler-tool-result-smoke] CASE: {name}")

    handler = ToolStepHandler(FakeExecutor(tool_result))
    result = handler.handle(
        step={"type": "tool", "tool_name": "fake_tool", "tool_input": {}},
        task=None,
        context=None,
        previous_result=None,
    )

    print(f"ok: {result.get('ok')}")
    print(f"error: {result.get('error')}")
    print(f"result: {result.get('result')}")

    if result.get("ok") is not expected_ok:
        return fail(f"{name}: expected ok {expected_ok}, got {result.get('ok')}")

    error = result.get("error")
    if expected_error_type is None:
        if error is not None:
            return fail(f"{name}: expected no error, got {error}")
    else:
        if not isinstance(error, dict):
            return fail(f"{name}: expected structured error dict, got {error}")
        if error.get("type") != expected_error_type:
            return fail(f"{name}: expected error type {expected_error_type}, got {error.get('type')}")
        if bool(error.get("retryable")) is not expected_retryable:
            return fail(f"{name}: expected retryable {expected_retryable}, got {error.get('retryable')}")

    normalized = result.get("result")
    if not isinstance(normalized, dict):
        return fail(f"{name}: normalized result is not dict")

    if "stdout_present" not in normalized:
        return fail(f"{name}: stdout_present missing")

    if "stderr_present" not in normalized:
        return fail(f"{name}: stderr_present missing")

    pass_step(f"{name} verified")
    return 0


def main() -> int:
    print("[step-handler-tool-result-smoke] START")

    cases = [
        (
            "dict_success",
            {"ok": True, "stdout": "hello", "returncode": 0},
            {
                "expected_ok": True,
                "expected_error_type": None,
            },
        ),
        (
            "json_string_success",
            '{"ok": true, "stdout": "hello from json", "returncode": 0}',
            {
                "expected_ok": True,
                "expected_error_type": None,
            },
        ),
        (
            "stderr_failure",
            {"ok": False, "stderr": "bad thing", "returncode": 1},
            {
                "expected_ok": False,
                "expected_error_type": "external_returncode_failed",
            },
        ),
        (
            "empty_output_retry_candidate",
            {"ok": True, "stdout": "", "stderr": "", "returncode": 0},
            {
                "expected_ok": False,
                "expected_error_type": "tool_empty_output",
                "expected_retryable": True,
            },
        ),
        (
            "non_dict_invalid",
            None,
            {
                "expected_ok": False,
                "expected_error_type": "tool_step_failed",
            },
        ),
    ]

    for name, payload, expected in cases:
        rc = run_case(name, payload, **expected)
        if rc != 0:
            return rc

    print("[step-handler-tool-result-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
