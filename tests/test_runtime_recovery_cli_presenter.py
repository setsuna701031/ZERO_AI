from __future__ import annotations

from core.runtime.runtime_recovery_cli_presenter import (
    RuntimeRecoveryCliPresenter,
    render_runtime_recovery_cli,
)


def test_cli_presenter_renders_ready_event() -> None:
    text = render_runtime_recovery_cli(
        {
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        }
    )

    assert "Runtime Recovery" in text
    assert "Readiness: ready" in text
    assert "Status: ready" in text
    assert "Summary: Recovery gate passed." in text


def test_cli_presenter_renders_blockers() -> None:
    text = RuntimeRecoveryCliPresenter().render(
        {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Recovery gate blocked.",
                "blockers": ["missing confirmation"],
            }
        }
    )

    assert "Readiness: blocked" in text
    assert "Blockers:" in text
    assert "- missing confirmation" in text


def test_cli_presenter_compact_mode() -> None:
    text = render_runtime_recovery_cli(
        {
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
        compact=True,
    )

    assert text == "[recovery:ready] Recovery gate passed."
