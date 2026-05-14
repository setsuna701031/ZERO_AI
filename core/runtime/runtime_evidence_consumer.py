from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


REQUIRED_RECORDS = ("snapshot", "replay", "audit", "rollback", "bundle")


class RuntimeEvidenceConsumer:
    """Read-only consumer for sealed runtime evidence.

    This layer normalizes the mainline seal into a compact, deterministic
    summary.  It does not mutate source records, write persistence, invoke
    replay, or make repair decisions.
    """

    SCHEMA = "zero.runtime_evidence.consumer_summary.v1"

    def read_seal(self, seal: Any) -> dict[str, Any]:
        if seal is None:
            return self.read_records({})

        records = self._safe_mapping(getattr(seal, "evidence_records", None))
        summary = self.read_records(
            records,
            seal_id=self._safe_text(getattr(seal, "seal_id", "")),
            seal_fingerprint=self._safe_text(getattr(seal, "fingerprint", "")),
            emission_order=self._emission_order(getattr(seal, "emitter", None)),
        )
        summary["events"] = {
            "scheduler": self._scheduler_events(getattr(seal, "scheduler_boundary", None)),
            "task_runtime": self._task_runtime_events(getattr(seal, "task_boundary", None)),
            "step_executor": self._step_executor_events(getattr(seal, "step_hook", None)),
        }
        summary["event_count"] = sum(
            int(value.get("count", 0))
            for value in summary["events"].values()
            if isinstance(value, dict)
        )
        summary["summary_fingerprint"] = self._fingerprint(summary)
        return self._copy(summary)

    def read_records(
        self,
        records: Any,
        *,
        seal_id: str = "",
        seal_fingerprint: str = "",
        emission_order: Any = None,
    ) -> dict[str, Any]:
        safe_records = self._safe_mapping(records)
        present_records = [
            name
            for name in REQUIRED_RECORDS
            if safe_records.get(name) is not None
        ]
        missing_records = [
            name
            for name in REQUIRED_RECORDS
            if safe_records.get(name) is None
        ]

        snapshot = safe_records.get("snapshot")
        replay = safe_records.get("replay")
        audit = safe_records.get("audit")
        rollback = safe_records.get("rollback")
        bundle = safe_records.get("bundle")

        record_refs = {
            "seal_id": self._safe_text(seal_id),
            "plan_id": self._first_text(
                getattr(bundle, "plan_id", ""),
                getattr(snapshot, "plan_id", ""),
                getattr(replay, "plan_id", ""),
                getattr(audit, "plan_id", ""),
                getattr(rollback, "plan_id", ""),
            ),
            "snapshot_id": self._first_text(
                getattr(bundle, "snapshot_id", ""),
                getattr(snapshot, "snapshot_id", ""),
                getattr(replay, "snapshot_id", ""),
                getattr(audit, "snapshot_id", ""),
                getattr(rollback, "snapshot_id", ""),
            ),
            "replay_id": self._safe_text(getattr(replay, "replay_id", "")),
            "audit_id": self._safe_text(getattr(audit, "audit_id", "")),
            "rollback_id": self._safe_text(getattr(rollback, "rollback_id", "")),
            "bundle_id": self._safe_text(getattr(bundle, "bundle_id", "")),
        }

        summary = {
            "ok": len(missing_records) == 0,
            "schema": self.SCHEMA,
            "seal_id": self._safe_text(seal_id),
            "seal_fingerprint": self._safe_text(seal_fingerprint),
            "record_count": len(present_records),
            "present_records": present_records,
            "missing_records": missing_records,
            "record_refs": record_refs,
            "aggregate_status": self._first_text(
                getattr(bundle, "aggregate_status", ""),
                getattr(snapshot, "status", ""),
                getattr(replay, "aggregate_status", ""),
                getattr(audit, "aggregate_status", ""),
                getattr(rollback, "aggregate_status", ""),
            ),
            "verification": {
                "replay": self._safe_text(getattr(replay, "verification_result", "")),
                "audit": self._safe_text(getattr(audit, "verification_result", "")),
                "rollback": self._safe_text(getattr(rollback, "verification_result", "")),
            },
            "execution_order": self._safe_list(getattr(snapshot, "execution_order", [])),
            "rollback_order": self._safe_list(getattr(rollback, "rollback_order", [])),
            "fingerprints": self._record_fingerprints(safe_records),
            "emission_order": self._safe_emission_order(emission_order),
            "events": {
                "scheduler": self._empty_event_summary(),
                "task_runtime": self._empty_event_summary(),
                "step_executor": self._empty_event_summary(),
            },
            "event_count": 0,
        }
        summary["can_replay"] = summary["verification"]["replay"] == "verified"
        summary["can_audit"] = summary["verification"]["audit"] == "verified"
        summary["can_rollback"] = summary["verification"]["rollback"] == "verified"
        summary["summary_fingerprint"] = self._fingerprint(summary)
        return self._copy(summary)

    def get_record_ref(self, summary: Any, ref_name: str) -> str:
        safe = self._safe_mapping(summary)
        refs = self._safe_mapping(safe.get("record_refs"))
        return self._safe_text(refs.get(ref_name))

    def can_replay(self, summary: Any) -> bool:
        return bool(self._safe_mapping(summary).get("can_replay", False))

    def can_audit(self, summary: Any) -> bool:
        return bool(self._safe_mapping(summary).get("can_audit", False))

    def can_rollback(self, summary: Any) -> bool:
        return bool(self._safe_mapping(summary).get("can_rollback", False))

    def _scheduler_events(self, boundary: Any) -> dict[str, Any]:
        return self._event_summary(
            self._list_events(boundary),
            phase_attr="orchestration_phase",
            status_attr="queue_name",
        )

    def _task_runtime_events(self, boundary: Any) -> dict[str, Any]:
        return self._event_summary(
            self._list_events(boundary),
            phase_attr="phase",
            status_attr="runtime_status",
        )

    def _step_executor_events(self, hook: Any) -> dict[str, Any]:
        return self._event_summary(
            self._list_events(hook),
            phase_attr="phase",
            status_attr="status",
        )

    def _event_summary(
        self,
        events: list[Any],
        *,
        phase_attr: str,
        status_attr: str,
    ) -> dict[str, Any]:
        return {
            "count": len(events),
            "phases": [
                self._safe_text(getattr(event, phase_attr, ""))
                for event in events
            ],
            "statuses": [
                self._safe_text(getattr(event, status_attr, ""))
                for event in events
            ],
            "fingerprints": [
                self._safe_text(getattr(event, "fingerprint", ""))
                for event in events
            ],
        }

    def _empty_event_summary(self) -> dict[str, Any]:
        return {
            "count": 0,
            "phases": [],
            "statuses": [],
            "fingerprints": [],
        }

    def _list_events(self, source: Any) -> list[Any]:
        list_events = getattr(source, "list_events", None)
        if not callable(list_events):
            return []
        try:
            events = list_events()
        except Exception:
            return []
        return [event for event in events if event is not None] if isinstance(events, list) else []

    def _record_fingerprints(self, records: dict[str, Any]) -> dict[str, str]:
        return {
            name: self._safe_text(getattr(records.get(name), "fingerprint", ""))
            for name in REQUIRED_RECORDS
        }

    def _emission_order(self, emitter: Any) -> list[dict[str, str]]:
        return self._safe_emission_order(getattr(emitter, "emission_order", None))

    def _safe_emission_order(self, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        order = []
        for item in value:
            if not isinstance(item, dict):
                continue
            order.append(
                {
                    "type": self._safe_text(item.get("type")),
                    "fingerprint": self._safe_text(item.get("fingerprint")),
                }
            )
        return order

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list[Any]:
        return copy.deepcopy(value) if isinstance(value, list) else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _first_text(self, *values: Any) -> str:
        for value in values:
            text = self._safe_text(value).strip()
            if text:
                return text
        return ""

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe_payload = self._copy(payload)
        safe_payload.pop("summary_fingerprint", None)
        encoded = json.dumps(
            safe_payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _copy(self, value: Any) -> Any:
        return copy.deepcopy(value)


def read_runtime_evidence_summary(seal: Any = None, records: Any = None) -> dict[str, Any]:
    consumer = RuntimeEvidenceConsumer()
    if seal is not None:
        return consumer.read_seal(seal)
    return consumer.read_records(records)


__all__ = [
    "RuntimeEvidenceConsumer",
    "read_runtime_evidence_summary",
]
