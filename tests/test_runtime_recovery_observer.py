from __future__ import annotations

from core.runtime.runtime_recovery_observer import (
    RuntimeRecoveryObserver,
    observe_runtime_recovery,
    render_runtime_recovery_observation,
)


def test_observer_reads_operator_summary_from_dict_payload() -> None:
    payload = {
        "operator_summary": {
            "ok": True,
            "status": "ready",
            "readiness": "ready",
            "summary": "Recovery gate passed.",
            "blockers": [],
        }
    }

    report = observe_runtime_recovery(payload)

    assert report["ok"] is True
    assert report["schema"] == RuntimeRecoveryObserver.SCHEMA
    assert report["read_only"] is True
    assert report["executes_recovery"] is False
    assert report["executes_rollback"] is False
    assert report["executes_repair"] is False
    assert report["readiness"] == "ready"
    assert report["status"] == "ready"
    assert report["summary"] == "Recovery gate passed."
    assert report["blockers"] == []


def test_observer_reads_operator_summary_from_report_object() -> None:
    class Report:
        payload = {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Recovery gate blocked runtime repair execution.",
                "blockers": ["missing confirmation"],
            }
        }

    report = observe_runtime_recovery(Report())

    assert report["ok"] is False
    assert report["readiness"] == "blocked"
    assert report["blockers"] == ["missing confirmation"]


def test_render_text_is_human_readable_and_read_only() -> None:
    text = render_runtime_recovery_observation(
        {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Recovery gate blocked runtime repair execution.",
                "blockers": ["blocked_contract"],
            }
        }
    )

    assert "Recovery readiness: blocked" in text
    assert "Summary: Recovery gate blocked runtime repair execution." in text
    assert "- blocked_contract" in text
