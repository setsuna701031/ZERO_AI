from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.mutation_audit import (
    MutationAuditEvent,
    MutationAuditRecord,
    read_audit_record,
)


@dataclass(frozen=True)
class MutationReplayStep:
    index: int
    event_type: str
    created_at: str
    payload_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationReplayTimeline:
    session_id: str
    reconstructed_at: str
    total_events: int
    steps: tuple[MutationReplayStep, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "reconstructed_at": self.reconstructed_at,
            "total_events": self.total_events,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
        )


def reconstruct_mutation_timeline(
    record: MutationAuditRecord,
) -> MutationReplayTimeline:
    if not record.events:
        raise ValueError(
            "Cannot reconstruct replay timeline from empty audit record."
        )

    steps: list[MutationReplayStep] = []

    for index, event in enumerate(record.events):
        summary = _build_payload_summary(event)

        steps.append(
            MutationReplayStep(
                index=index,
                event_type=event.event_type,
                created_at=event.created_at,
                payload_summary=summary,
            )
        )

    return MutationReplayTimeline(
        session_id=record.session_id,
        reconstructed_at=_utc_now(),
        total_events=len(steps),
        steps=tuple(steps),
        metadata=dict(record.metadata),
    )


def reconstruct_mutation_timeline_from_file(
    path: str | Path,
) -> MutationReplayTimeline:
    record = read_audit_record(path)
    return reconstruct_mutation_timeline(record)


def write_replay_timeline(
    timeline: MutationReplayTimeline,
    directory: str | Path,
    filename: str = "mutation_replay_timeline.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    target_path = target_dir / filename

    target_path.write_text(
        timeline.to_json(),
        encoding="utf-8",
    )

    return target_path


def read_replay_timeline(
    path: str | Path,
) -> MutationReplayTimeline:
    data = json.loads(
        Path(path).read_text(encoding="utf-8")
    )

    steps = tuple(
        MutationReplayStep(
            index=int(item["index"]),
            event_type=str(item["event_type"]),
            created_at=str(item["created_at"]),
            payload_summary=dict(
                item.get("payload_summary") or {}
            ),
        )
        for item in data.get("steps", [])
    )

    return MutationReplayTimeline(
        session_id=str(data["session_id"]),
        reconstructed_at=str(
            data["reconstructed_at"]
        ),
        total_events=int(data["total_events"]),
        steps=steps,
        metadata=dict(data.get("metadata") or {}),
    )


def replay_event_types(
    timeline: MutationReplayTimeline,
) -> tuple[str, ...]:
    return tuple(
        step.event_type
        for step in timeline.steps
    )


def _build_payload_summary(
    event: MutationAuditEvent,
) -> dict[str, Any]:
    payload = event.payload

    summary: dict[str, Any] = {}

    if "status" in payload:
        summary["status"] = payload["status"]

    if "approval_mode" in payload:
        summary["approval_mode"] = payload["approval_mode"]

    if "verification_requirement" in payload:
        summary["verification_requirement"] = payload[
            "verification_requirement"
        ]

    if "applied_paths" in payload:
        summary["applied_paths"] = payload[
            "applied_paths"
        ]

    if "items" in payload:
        summary["patch_items"] = len(
            payload["items"]
        )

    if "checks" in payload:
        summary["checks"] = len(
            payload["checks"]
        )

    return summary


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()