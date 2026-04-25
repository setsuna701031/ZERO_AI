from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_route_policy import detect_document_flow_capability


def fail(message: str) -> int:
    print(f"[agent-route-policy-capability-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[agent-route-policy-capability-smoke] PASS: {message}")


def check_case(user_input: str, expected_matched: bool, expected_operation: str, label: str) -> bool:
    result = detect_document_flow_capability(user_input)

    matched = bool(result.get("matched"))
    operation = str(result.get("operation") or "")

    if matched != expected_matched:
        print(f"[agent-route-policy-capability-smoke] case failed: {label}")
        print(f"expected matched: {expected_matched}")
        print(f"actual matched:   {matched}")
        print(f"result: {result}")
        return False

    if operation != expected_operation:
        print(f"[agent-route-policy-capability-smoke] case failed: {label}")
        print(f"expected operation: {expected_operation}")
        print(f"actual operation:   {operation}")
        print(f"result: {result}")
        return False

    pass_step(label)
    return True


def main() -> int:
    print("[agent-route-policy-capability-smoke] START")

    checks = [
        check_case(
            "summarize workspace/shared/input.txt into workspace/shared/summary.txt",
            True,
            "summary",
            "summary document flow detected",
        ),
        check_case(
            "extract action items from workspace/shared/input.txt into workspace/shared/action_items.txt",
            True,
            "action_items",
            "action-items document flow detected",
        ),
        check_case(
            "read workspace/shared/input.txt and produce summary and action items",
            True,
            "summary_and_action_items",
            "summary + action-items document flow detected",
        ),
        check_case(
            "summarize this meeting note",
            False,
            "",
            "no document path does not match",
        ),
        check_case(
            "read workspace/shared/input.txt",
            False,
            "",
            "document path without supported operation does not match",
        ),
    ]

    if not all(checks):
        return fail("one or more route policy capability checks failed")

    print("[agent-route-policy-capability-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())