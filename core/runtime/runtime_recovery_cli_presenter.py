from __future__ import annotations

from typing import Any

from core.runtime.runtime_recovery_event_schema import build_runtime_recovery_event


class RuntimeRecoveryCliPresenter:
    """Render runtime recovery events for terminal/CLI output only."""

    def render(self, source: Any, *, compact: bool = False) -> str:
        event = build_runtime_recovery_event(source=source)

        readiness = str(event.get("readiness") or "unknown")
        status = str(event.get("status") or "unknown")
        summary = str(event.get("summary") or "")
        blockers = event.get("blockers")
        blockers = blockers if isinstance(blockers, list) else []

        if compact:
            return f"[recovery:{readiness}] {summary}".strip()

        lines = [
            "Runtime Recovery",
            f"Readiness: {readiness}",
            f"Status: {status}",
            f"Summary: {summary}",
        ]

        if blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item}" for item in blockers)

        return "\n".join(lines)


def render_runtime_recovery_cli(source: Any, *, compact: bool = False) -> str:
    return RuntimeRecoveryCliPresenter().render(source, compact=compact)


__all__ = [
    "RuntimeRecoveryCliPresenter",
    "render_runtime_recovery_cli",
]
