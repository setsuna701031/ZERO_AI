from __future__ import annotations

from typing import Any, Dict


DEFAULT_LANGUAGE = "zh-TW"
SUPPORTED_LANGUAGES = {"en", "zh-TW"}


STATUS_LABELS: Dict[str, Dict[str, str]] = {
    "queued": {"en": "Queued", "zh-TW": "排隊中"},
    "planning": {"en": "Planning", "zh-TW": "規劃中"},
    "ready": {"en": "Ready", "zh-TW": "就緒"},
    "running": {"en": "Running", "zh-TW": "執行中"},
    "waiting": {"en": "Waiting", "zh-TW": "等待中"},
    "blocked": {"en": "Blocked", "zh-TW": "已阻擋"},
    "retrying": {"en": "Retrying", "zh-TW": "重試中"},
    "replanning": {"en": "Replanning", "zh-TW": "重新規劃中"},
    "paused": {"en": "Paused", "zh-TW": "已暫停"},
    "finished": {"en": "Finished", "zh-TW": "已完成"},
    "failed": {"en": "Failed", "zh-TW": "失敗"},
    "cancelled": {"en": "Cancelled", "zh-TW": "已取消"},
    "timeout": {"en": "Timeout", "zh-TW": "逾時"},
}


EVENT_LABELS: Dict[str, Dict[str, str]] = {
    "task_created": {"en": "Task created", "zh-TW": "任務已建立"},
    "task_submitted": {"en": "Task submitted", "zh-TW": "任務已提交"},
    "task_started": {"en": "Task started", "zh-TW": "任務已開始"},
    "task_finished": {"en": "Task finished", "zh-TW": "任務已完成"},
    "task_failed": {"en": "Task failed", "zh-TW": "任務失敗"},
    "step_completed": {"en": "Step completed", "zh-TW": "步驟已完成"},
    "capability_executed": {"en": "Capability executed", "zh-TW": "能力已執行"},
    "capability_failed": {"en": "Capability failed", "zh-TW": "能力執行失敗"},
    "file_written": {"en": "File written", "zh-TW": "檔案已寫入"},
    "file_read": {"en": "File read", "zh-TW": "檔案已讀取"},
    "verify_passed": {"en": "Verify passed", "zh-TW": "驗證通過"},
    "verify_failed": {"en": "Verify failed", "zh-TW": "驗證失敗"},
    "guard_blocked": {"en": "Guard blocked", "zh-TW": "安全防護已阻擋"},
    "already_finished": {"en": "Already finished", "zh-TW": "已完成"},
}


FIELD_LABELS: Dict[str, Dict[str, str]] = {
    "status": {"en": "Status", "zh-TW": "狀態"},
    "state": {"en": "State", "zh-TW": "狀態"},
    "reason": {"en": "Reason", "zh-TW": "原因"},
    "source": {"en": "Source", "zh-TW": "來源"},
    "detail": {"en": "Detail", "zh-TW": "細節"},
    "task_id": {"en": "Task ID", "zh-TW": "任務 ID"},
    "task": {"en": "Task", "zh-TW": "任務"},
    "operation": {"en": "Operation", "zh-TW": "操作"},
    "capability": {"en": "Capability", "zh-TW": "能力"},
    "final_answer": {"en": "Final Answer", "zh-TW": "最終結果"},
    "error": {"en": "Error", "zh-TW": "錯誤"},
}


def normalize_language(language: Any = None) -> str:
    value = str(language or DEFAULT_LANGUAGE).strip()
    if value in SUPPORTED_LANGUAGES:
        return value

    lowered = value.lower()
    if lowered in {"zh", "zh_tw", "zh-tw", "tw", "traditional_chinese"}:
        return "zh-TW"

    if lowered in {"en", "en-us", "english"}:
        return "en"

    return DEFAULT_LANGUAGE


def normalize_key(value: Any) -> str:
    return str(value or "").strip()


def translate_from_table(table: Dict[str, Dict[str, str]], key: Any, language: Any = None) -> str:
    normalized_key = normalize_key(key)
    if not normalized_key:
        return ""

    lang = normalize_language(language)
    entry = table.get(normalized_key)
    if not isinstance(entry, dict):
        return normalized_key

    translated = str(entry.get(lang) or "").strip()
    if translated:
        return translated

    fallback = str(entry.get("en") or "").strip()
    if fallback:
        return fallback

    return normalized_key


def translate_status(status: Any, language: Any = None) -> str:
    return translate_from_table(STATUS_LABELS, status, language)


def translate_event(event: Any, language: Any = None) -> str:
    return translate_from_table(EVENT_LABELS, event, language)


def translate_field(field: Any, language: Any = None) -> str:
    return translate_from_table(FIELD_LABELS, field, language)


def status_label(status: Any, language: Any = None) -> str:
    return translate_status(status, language)


def event_label(event: Any, language: Any = None) -> str:
    return translate_event(event, language)


def field_label(field: Any, language: Any = None) -> str:
    return translate_field(field, language)


def decorate_status(status: Any, language: Any = None) -> Dict[str, str]:
    raw = normalize_key(status)
    return {
        "raw": raw,
        "label": translate_status(raw, language),
        "language": normalize_language(language),
    }


def decorate_event(event: Any, language: Any = None) -> Dict[str, str]:
    raw = normalize_key(event)
    return {
        "raw": raw,
        "label": translate_event(raw, language),
        "language": normalize_language(language),
    }


def decorate_runtime_state(runtime_state: Any, language: Any = None) -> Dict[str, Any]:
    if not isinstance(runtime_state, dict):
        return {}

    lang = normalize_language(language)
    status = normalize_key(runtime_state.get("status"))

    decorated = dict(runtime_state)
    decorated["status_label"] = translate_status(status, lang)
    decorated["display_language"] = lang

    return decorated


def main() -> int:
    print("[display-i18n] status labels")
    for status in ("queued", "running", "finished", "failed", "blocked"):
        print(f"{status} -> {translate_status(status, 'zh-TW')} / {translate_status(status, 'en')}")

    print("[display-i18n] event labels")
    for event in ("task_created", "capability_executed", "guard_blocked"):
        print(f"{event} -> {translate_event(event, 'zh-TW')} / {translate_event(event, 'en')}")

    print("[display-i18n] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
