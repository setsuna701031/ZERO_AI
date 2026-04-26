from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.display.i18n import (
    decorate_event,
    decorate_runtime_state,
    decorate_status,
    normalize_language,
    translate_event,
    translate_field,
    translate_status,
)


def fail(message: str) -> int:
    print(f"[display-i18n-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[display-i18n-smoke] PASS: {message}")


def assert_equal(actual, expected, label: str) -> bool:
    if actual != expected:
        print(f"[display-i18n-smoke] mismatch {label}: expected {expected!r}, got {actual!r}")
        return False
    pass_step(label)
    return True


def main() -> int:
    print("[display-i18n-smoke] START")

    checks = [
        assert_equal(normalize_language("zh"), "zh-TW", "normalize zh"),
        assert_equal(normalize_language("en-us"), "en", "normalize en-us"),
        assert_equal(translate_status("queued", "zh-TW"), "排隊中", "queued zh-TW"),
        assert_equal(translate_status("running", "zh-TW"), "執行中", "running zh-TW"),
        assert_equal(translate_status("finished", "zh-TW"), "已完成", "finished zh-TW"),
        assert_equal(translate_status("failed", "zh-TW"), "失敗", "failed zh-TW"),
        assert_equal(translate_status("blocked", "zh-TW"), "已阻擋", "blocked zh-TW"),
        assert_equal(translate_status("queued", "en"), "Queued", "queued en"),
        assert_equal(translate_event("capability_executed", "zh-TW"), "能力已執行", "capability_executed zh-TW"),
        assert_equal(translate_event("guard_blocked", "zh-TW"), "安全防護已阻擋", "guard_blocked zh-TW"),
        assert_equal(translate_field("status", "zh-TW"), "狀態", "field status zh-TW"),
        assert_equal(translate_status("unknown_status", "zh-TW"), "unknown_status", "unknown fallback"),
    ]

    decorated_status = decorate_status("running", "zh-TW")
    checks.append(assert_equal(decorated_status.get("raw"), "running", "decorate_status raw"))
    checks.append(assert_equal(decorated_status.get("label"), "執行中", "decorate_status label"))

    decorated_event = decorate_event("task_created", "zh-TW")
    checks.append(assert_equal(decorated_event.get("raw"), "task_created", "decorate_event raw"))
    checks.append(assert_equal(decorated_event.get("label"), "任務已建立", "decorate_event label"))

    runtime_state = decorate_runtime_state({"status": "finished", "task_id": "task_demo"}, "zh-TW")
    checks.append(assert_equal(runtime_state.get("status"), "finished", "runtime_state raw status"))
    checks.append(assert_equal(runtime_state.get("status_label"), "已完成", "runtime_state status_label"))
    checks.append(assert_equal(runtime_state.get("display_language"), "zh-TW", "runtime_state display_language"))

    if not all(checks):
        return fail("one or more i18n checks failed")

    print("[display-i18n-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())