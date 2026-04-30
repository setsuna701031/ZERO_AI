from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.model_use_policy import add_policy_hint, classify_model_use


PREFIX = "[model-use-policy-smoke]"


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

    non_dict_decision = ("route", "direct_response")
    if add_policy_hint(non_dict_decision, "write file") != non_dict_decision:
        return fail("non-dict decision fallback changed original decision value")
    pass_step("policy_hint is optional for unsupported decision shapes")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
