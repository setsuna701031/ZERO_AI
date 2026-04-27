from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.local_observer import observe_result


def fail(message: str) -> int:
    print(f"[local-observer-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[local-observer-smoke] PASS: {message}")


def assert_observation(
    name: str,
    payload: Any,
    *,
    expected_ok: bool,
    expected_status: str,
    expected_error_type: str | None,
    expected_replan: bool,
    expected_fail: bool,
    expected_terminal: bool,
) -> int:
    print(f"[local-observer-smoke] CASE: {name}")
    observation = observe_result(payload)

    for key in (
        "ok",
        "status",
        "action",
        "error",
        "error_type",
        "returncode",
        "stdout_present",
        "stderr_present",
        "terminal",
        "should_retry_candidate",
        "should_replan_candidate",
        "should_fail_candidate",
    ):
        print(f"{key}: {observation.get(key)}")

    if observation.get("ok") is not expected_ok:
        return fail(f"{name}: expected ok {expected_ok}, got {observation.get('ok')}")

    if observation.get("status") != expected_status:
        return fail(f"{name}: expected status {expected_status}, got {observation.get('status')}")

    if observation.get("error_type") != expected_error_type:
        return fail(f"{name}: expected error_type {expected_error_type}, got {observation.get('error_type')}")

    if observation.get("should_replan_candidate") is not expected_replan:
        return fail(
            f"{name}: expected should_replan_candidate {expected_replan}, got {observation.get('should_replan_candidate')}"
        )

    if observation.get("should_fail_candidate") is not expected_fail:
        return fail(
            f"{name}: expected should_fail_candidate {expected_fail}, got {observation.get('should_fail_candidate')}"
        )

    if observation.get("terminal") is not expected_terminal:
        return fail(f"{name}: expected terminal {expected_terminal}, got {observation.get('terminal')}")

    pass_step(f"{name} verified")
    return 0


def main() -> int:
    print("[local-observer-smoke] START")

    cases = [
        (
            "finished_success",
            {
                "ok": True,
                "status": "finished",
                "action": "already_finished",
                "final_answer": "done",
            },
            {
                "expected_ok": True,
                "expected_status": "finished",
                "expected_error_type": None,
                "expected_replan": False,
                "expected_fail": False,
                "expected_terminal": True,
            },
        ),
        (
            "running_success",
            {
                "ok": True,
                "status": "running",
                "action": "step_completed",
                "runtime_state": {
                    "status": "running",
                    "last_step_result": {
                        "ok": True,
                        "stdout": "hello",
                    },
                },
            },
            {
                "expected_ok": True,
                "expected_status": "running",
                "expected_error_type": None,
                "expected_replan": False,
                "expected_fail": False,
                "expected_terminal": False,
            },
        ),
        (
            "verify_target_not_found",
            {
                "ok": False,
                "status": "failed",
                "action": "step_failed",
                "error": "verify target not found: workspace/shared/missing.txt",
            },
            {
                "expected_ok": False,
                "expected_status": "failed",
                "expected_error_type": "verify_target_not_found",
                "expected_replan": True,
                "expected_fail": False,
                "expected_terminal": True,
            },
        ),
        (
            "guard_blocked",
            {
                "ok": False,
                "status": "blocked",
                "action": "guard_blocked",
                "error": "blocked by execution guard",
            },
            {
                "expected_ok": False,
                "expected_status": "blocked",
                "expected_error_type": "guard_blocked",
                "expected_replan": False,
                "expected_fail": True,
                "expected_terminal": True,
            },
        ),
        (
            "command_returncode_failure",
            {
                "ok": True,
                "status": "failed",
                "action": "command_failed",
                "result": {
                    "returncode": 2,
                    "stdout": "",
                    "stderr": "command failed",
                },
            },
            {
                "expected_ok": False,
                "expected_status": "failed",
                "expected_error_type": "command_failed",
                "expected_replan": True,
                "expected_fail": False,
                "expected_terminal": True,
            },
        ),
        (
            "invalid_non_dict",
            "not a dict",
            {
                "expected_ok": False,
                "expected_status": "failed",
                "expected_error_type": "tool_result_invalid",
                "expected_replan": True,
                "expected_fail": False,
                "expected_terminal": True,
            },
        ),
    ]

    for name, payload, expected in cases:
        result = assert_observation(name, payload, **expected)
        if result != 0:
            return result

    print("[local-observer-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
