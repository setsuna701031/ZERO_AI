from __future__ import annotations

from core.tasks.runtime_kernel_events import normalize_runtime_kernel_events
from core.tasks.runtime_kernel_timeline import (
    build_runtime_timeline,
    get_failed_timeline_events,
    get_first_timeline_event,
    get_latest_timeline_event,
    summarize_runtime_timeline,
)


def test_build_runtime_timeline_returns_empty_for_none_or_empty_list():
    assert build_runtime_timeline(None) == []
    assert build_runtime_timeline([]) == []


def test_build_runtime_timeline_accepts_malformed_event_with_safe_fallback():
    timeline = build_runtime_timeline(["bad-event"])

    assert len(timeline) == 1
    assert timeline[0]["sequence_index"] == 0
    assert timeline[0]["source"] == "unknown"
    assert timeline[0]["event_type"] == "unknown_event"
    assert timeline[0]["status"] == "unknown"
    assert timeline[0]["summary"] == "malformed event"
    assert timeline[0]["raw"] == "bad-event"


def test_build_runtime_timeline_sorts_parseable_timestamps():
    events = normalize_runtime_kernel_events(
        [
            {"event": "second", "source": "runtime", "timestamp": "2026-05-10T10:00:02Z"},
            {"event": "first", "source": "runtime", "timestamp": "2026-05-10T10:00:01Z"},
            {"event": "third", "source": "runtime", "timestamp": 1778407203},
        ]
    )

    timeline = build_runtime_timeline(events)

    assert [item["event_type"] for item in timeline] == ["first", "second", "third"]
    assert [item["sequence_index"] for item in timeline] == [0, 1, 2]


def test_build_runtime_timeline_keeps_missing_timestamp_order_after_timed_events():
    events = normalize_runtime_kernel_events(
        [
            {"event": "missing-a", "source": "runtime"},
            {"event": "timed", "source": "runtime", "ts": 1},
            {"event": "missing-b", "source": "runtime"},
        ]
    )

    timeline = build_runtime_timeline(events)

    assert [item["event_type"] for item in timeline] == ["timed", "missing-a", "missing-b"]
    assert [item["sequence_index"] for item in timeline] == [0, 1, 2]


def test_timeline_items_preserve_required_fields_and_raw_traceability():
    raw = {"event": "execution_step_rejected", "result_error": "missing path", "ts": 10}
    timeline = build_runtime_timeline(normalize_runtime_kernel_events([raw]))
    item = timeline[0]

    assert set(item) >= {
        "sequence_index",
        "source",
        "event_type",
        "status",
        "summary",
        "timestamp",
        "raw",
    }
    assert item["raw"] == raw


def test_timeline_helpers_return_first_latest_and_failed_events():
    events = normalize_runtime_kernel_events(
        [
            {"event": "planned", "source": "planner", "ts": 1, "ok": True},
            {"event": "execution_step_rejected", "source": "execution", "ts": 2, "result_error": "boom"},
            {"event": "repair_patch_planned", "source": "repair", "ts": 3},
        ]
    )
    timeline = build_runtime_timeline(events)

    assert get_first_timeline_event(timeline)["event_type"] == "planned"
    assert get_latest_timeline_event(timeline)["event_type"] == "repair_patch_planned"
    failed = get_failed_timeline_events(timeline)
    assert len(failed) == 1
    assert failed[0]["event_type"] == "execution_step_rejected"


def test_summarize_runtime_timeline_counts_sources_statuses_and_boundaries():
    timeline = build_runtime_timeline(
        normalize_runtime_kernel_events(
            [
                {"event": "planned", "source": "planner", "ts": 1, "ok": True},
                {"event": "task_blocked", "blocked_reason": "review required", "ts": 2},
                {"event": "runtime_step_started", "source": "runtime"},
            ]
        )
    )
    summary = summarize_runtime_timeline(timeline)

    assert summary["ok"] is True
    assert summary["event_count"] == 3
    assert summary["failed_event_count"] == 1
    assert summary["first_event"]["event_type"] == "planned"
    assert summary["latest_event"]["event_type"] == "runtime_step_started"
    assert summary["by_source"]["planner"] == 1
    assert summary["by_source"]["blocker"] == 1
    assert summary["by_status"]["blocked"] == 1
