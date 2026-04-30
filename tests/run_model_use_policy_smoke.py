from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.model_use_policy import (
    add_policy_hint,
    classify_model_use,
    format_policy_hint_display,
    policy_hint_trace_event,
)


PREFIX = "[model-use-policy-smoke]"
BEHAVIOR_KEYS = (
    "decision",
    "route",
    "mode",
    "task",
    "next_action",
    "should_queue",
    "should_run",
    "should_approve",
    "queued",
    "approved",
    "tool",
    "model",
    "planner",
)


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def assert_classification(request: object, expected: str, label: str) -> int:
    result = classify_model_use(request)
    actual = result.get("classification")
    reason = result.get("reason")

    if actual != expected:
        print(f"{PREFIX} case failed: {label}")
        print(f"expected classification: {expected}")
        print(f"actual classification:   {actual}")
        print(f"reason: {reason}")
        print(f"result: {result}")
        return 1

    if not isinstance(reason, str) or not reason:
        return fail(f"{label}: missing reason")

    if set(result.keys()) != {"classification", "reason"}:
        return fail(f"{label}: policy returned unexpected keys: {sorted(result.keys())}")

    pass_step(label)
    return 0


def behavior_signature(decision: dict) -> dict:
    return {key: decision.get(key) for key in BEHAVIOR_KEYS}


def main() -> int:
    print(f"{PREFIX} START")

    cases = [
        (
            {"operation": "json_parse", "input": '{"ok": true}'},
            "rule_only",
            "valid JSON parsing is allowlisted rule_only",
        ),
        (
            {"operation": "normalize_path", "input": "workspace/../workspace/file.txt"},
            "rule_only",
            "path normalization is allowlisted rule_only",
        ),
        (
            {"operation": "format_log", "input": "INFO started"},
            "rule_only",
            "log formatting is allowlisted rule_only",
        ),
        (
            {"operation": "planning", "input": "plan the implementation"},
            "large_model_required",
            "planning is not rule_only",
        ),
        (
            "choose best option",
            "small_model_allowed",
            "ambiguous decision phrase is not rule_only",
        ),
        (
            "repair invalid JSON while preserving intent",
            "small_model_allowed",
            "intent preservation is not rule_only",
        ),
        (
            {"operation": "file_write", "input": "write report.md"},
            "requires_confirmation",
            "file write requires confirmation",
        ),
        (
            "execute this task",
            "requires_confirmation",
            "execution requires confirmation",
        ),
        (
            "maybe clean this data",
            "small_model_allowed",
            "unclear clean data request does not become rule_only",
        ),
        (
            {"operation": "unknown_transform", "input": "do the thing"},
            "requires_confirmation",
            "unknown operation fails closed",
        ),
    ]

    for request, expected, label in cases:
        check = assert_classification(request, expected, label)
        if check != 0:
            return check

    before = {"operation": "json_parse", "input": '{"same": true}'}
    after = dict(before)
    first = classify_model_use(before)
    second = classify_model_use(before)
    if first != second:
        return fail("same input produced different output")
    if before != after:
        return fail("classification mutated input task")
    pass_step("classification is deterministic and does not mutate input")

    serialized = repr(first).lower()
    forbidden_model_fragments = ("gpt", "claude", "gemini", "llama", "mistral")
    if any(fragment in serialized for fragment in forbidden_model_fragments):
        return fail("policy selected or leaked a concrete model name")
    pass_step("classification does not select concrete model names")

    route_decision = {
        "decision": "chat",
        "route": "direct_response",
        "mode": "chat",
        "task": False,
        "tool": "",
        "model": "",
        "queued": False,
        "approved": False,
        "nested": {"status": "stable"},
    }
    route_before = {
        "decision": "chat",
        "route": "direct_response",
        "mode": "chat",
        "task": False,
        "tool": "",
        "model": "",
        "queued": False,
        "approved": False,
        "nested": {"status": "stable"},
    }
    hinted = add_policy_hint(route_decision, "write file workspace/report.md")
    if route_decision != route_before:
        return fail("add_policy_hint mutated original route decision")
    if hinted is route_decision:
        return fail("add_policy_hint returned original decision object")
    if not isinstance(hinted, dict):
        return fail("add_policy_hint did not return a decision dict")
    if hinted.get("policy_hint", {}).get("classification") != "requires_confirmation":
        return fail("policy_hint did not record requires_confirmation classification")

    for key, expected in route_before.items():
        if hinted.get(key) != expected:
            return fail(f"policy_hint changed original decision field {key!r}")
    pass_step("requires_confirmation policy_hint leaves route decision unchanged")

    hinted["nested"]["status"] = "changed"
    if route_decision["nested"]["status"] != "stable":
        return fail("add_policy_hint did not deep-copy nested decision data")
    pass_step("add_policy_hint returns a deep decision copy")

    trace_event = policy_hint_trace_event(hinted)
    expected_event = {
        "event": "policy_hint_attached",
        "classification": "requires_confirmation",
        "reason": "risk_requires_confirmation",
    }
    if trace_event != expected_event:
        return fail(f"policy_hint trace event mismatch: {trace_event}")
    if any(key in trace_event for key in ("decision", "route", "mode", "task", "tool", "model")):
        return fail("policy_hint trace event leaked control fields")
    pass_step("policy_hint emits read-only trace metadata")

    display = format_policy_hint_display(hinted)
    if display != "[policy] requires_confirmation - risk_requires_confirmation":
        return fail(f"policy_hint display mismatch: {display!r}")
    pass_step("policy_hint emits UI/CLI display text only")

    base_behavior_decision = {
        "decision": "task",
        "route": "planner",
        "mode": "task",
        "task": True,
        "next_action": "queue",
        "should_queue": True,
        "should_run": False,
        "should_approve": False,
        "queued": False,
        "approved": False,
        "tool": "existing_tool_choice",
        "model": "existing_model_choice",
        "planner": "existing_planner_choice",
    }
    behavior_cases = [
        ({"operation": "json_parse", "input": "{}"}, "rule_only"),
        ("repair invalid JSON while preserving intent", "small_model_allowed"),
        ("plan the implementation", "large_model_required"),
        ("write file workspace/report.md", "requires_confirmation"),
    ]
    expected_signature = behavior_signature(base_behavior_decision)
    for user_input, expected_classification in behavior_cases:
        hinted_decision = add_policy_hint(base_behavior_decision, user_input)
        if behavior_signature(hinted_decision) != expected_signature:
            return fail(
                "policy_hint changed behavior fields for "
                f"{expected_classification}: {behavior_signature(hinted_decision)}"
            )
        actual_classification = hinted_decision.get("policy_hint", {}).get("classification")
        if actual_classification != expected_classification:
            return fail(
                f"expected {expected_classification} hint, got {actual_classification}"
            )
    pass_step("all policy_hint classifications leave behavior fields unchanged")

    same_task = {
        "decision": "task",
        "route": "planner",
        "mode": "task",
        "task": True,
        "next_action": "queue",
        "should_queue": True,
        "should_run": False,
        "should_approve": False,
        "queued": False,
        "approved": False,
        "tool": "existing_tool_choice",
        "model": "existing_model_choice",
        "planner": "existing_planner_choice",
    }
    forced_hint_cases = [
        {
            **same_task,
            "policy_hint": {
                "classification": "rule_only",
                "reason": "allowlisted_deterministic_operation",
            },
        },
        {
            **same_task,
            "policy_hint": {
                "classification": "small_model_allowed",
                "reason": "light_interpretation_or_extraction_allows_small_model",
            },
        },
        {
            **same_task,
            "policy_hint": {
                "classification": "large_model_required",
                "reason": "planning_or_reasoning_requires_large_model",
            },
        },
        {
            **same_task,
            "policy_hint": {
                "classification": "requires_confirmation",
                "reason": "risk_requires_confirmation",
            },
        },
    ]
    forced_signature = behavior_signature(forced_hint_cases[0])
    for forced_case in forced_hint_cases[1:]:
        if behavior_signature(forced_case) != forced_signature:
            return fail(
                "different forced policy_hint classifications changed behavior signature"
            )
    pass_step("same task behavior signature ignores forced policy_hint differences")

    non_dict_decision = ("route", "direct_response")
    if add_policy_hint(non_dict_decision, "write file") != non_dict_decision:
        return fail("non-dict decision fallback changed original decision value")
    pass_step("policy_hint is optional for unsupported decision shapes")

    if policy_hint_trace_event({"decision": "chat"}) != {}:
        return fail("missing policy_hint should not emit trace metadata")
    if format_policy_hint_display({"decision": "chat"}) != "":
        return fail("missing policy_hint should not emit display text")
    pass_step("missing policy_hint remains observationally optional")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
