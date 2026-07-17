from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayRecord
from core.runtime.rollback_verification import RollbackVerificationRecord
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle


REQUIRED_RECORDS = ("snapshot", "replay", "audit", "rollback", "bundle")
REQUIRED_RECORD_TYPES = {
    "snapshot": ExecutionPlanSnapshot,
    "replay": ExecutionReplayRecord,
    "audit": ExecutionAuditRecord,
    "rollback": RollbackVerificationRecord,
    "bundle": RuntimeEvidenceBundle,
}
EXTERNAL_RECORD_TYPES = {
    "snapshot": "execution_plan_snapshot",
    "replay": "execution_replay_record",
    "audit": "execution_audit_record",
    "rollback": "rollback_verification_record",
    "bundle": "runtime_evidence_bundle",
}
SEAL_ACCEPTED_PRODUCER_LAYERS = {"governed_execution", "step_executor"}


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
        invalid_records = [
            name
            for name in REQUIRED_RECORDS
            if safe_records.get(name) is not None and not self._valid_record(name, safe_records.get(name))
        ]
        present_records = [
            name
            for name in REQUIRED_RECORDS
            if self._valid_record(name, safe_records.get(name))
        ]
        missing_records = [
            name
            for name in REQUIRED_RECORDS
            if not self._valid_record(name, safe_records.get(name))
        ]
        record_classifications = {
            name: self._record_classification(name, safe_records.get(name))
            for name in REQUIRED_RECORDS
        }
        invalid_reasons = {
            name: self._invalid_record_reasons(name, safe_records.get(name))
            for name in invalid_records
        }

        snapshot = safe_records.get("snapshot")
        replay = safe_records.get("replay")
        audit = safe_records.get("audit")
        rollback = safe_records.get("rollback")
        bundle = safe_records.get("bundle")

        record_refs = {
            "seal_id": self._safe_text(seal_id),
            "plan_id": self._first_text(
                self._record_field(bundle, "plan_id"),
                self._record_field(snapshot, "plan_id"),
                self._record_field(replay, "plan_id"),
                self._record_field(audit, "plan_id"),
                self._record_field(rollback, "plan_id"),
            ),
            "snapshot_id": self._first_text(
                self._record_field(bundle, "snapshot_id"),
                self._record_field(snapshot, "snapshot_id"),
                self._record_field(replay, "snapshot_id"),
                self._record_field(audit, "snapshot_id"),
                self._record_field(rollback, "snapshot_id"),
            ),
            "replay_id": self._safe_text(self._record_field(replay, "replay_id")),
            "audit_id": self._safe_text(self._record_field(audit, "audit_id")),
            "rollback_id": self._safe_text(self._record_field(rollback, "rollback_id")),
            "bundle_id": self._safe_text(self._record_field(bundle, "bundle_id")),
        }

        summary = {
            "ok": len(missing_records) == 0,
            "schema": self.SCHEMA,
            "seal_id": self._safe_text(seal_id),
            "seal_fingerprint": self._safe_text(seal_fingerprint),
            "record_count": len(present_records),
            "present_records": present_records,
            "missing_records": missing_records,
            "invalid_records": invalid_records,
            "invalid_record_reasons": invalid_reasons,
            "record_classifications": record_classifications,
            "record_refs": record_refs,
            "aggregate_status": self._first_text(
                self._record_field(bundle, "aggregate_status"),
                self._record_field(snapshot, "status"),
                self._record_field(replay, "aggregate_status"),
                self._record_field(audit, "aggregate_status"),
                self._record_field(rollback, "aggregate_status"),
            ),
            "verification": {
                "replay": self._safe_text(self._record_field(replay, "verification_result")),
                "audit": self._safe_text(self._record_field(audit, "verification_result")),
                "rollback": self._safe_text(self._record_field(rollback, "verification_result")),
            },
            "execution_order": self._safe_list(self._record_field(snapshot, "execution_order")),
            "rollback_order": self._safe_list(self._record_field(rollback, "rollback_order")),
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
            name: self._safe_text(self._record_field(records.get(name), "fingerprint"))
            if self._valid_record(name, records.get(name))
            else ""
            for name in REQUIRED_RECORDS
        }

    def _valid_record(self, name: str, value: Any) -> bool:
        expected_type = REQUIRED_RECORD_TYPES.get(name)
        if expected_type is not None and isinstance(value, expected_type):
            return True
        return self._external_record_validation(name, value)["accepted"]

    def _record_classification(self, name: str, value: Any) -> str:
        if value is None:
            return "missing"
        expected_type = REQUIRED_RECORD_TYPES.get(name)
        if expected_type is not None and isinstance(value, expected_type):
            return "governed_runtime_evidence"
        validation = self._external_record_validation(name, value)
        if validation["accepted"]:
            producer_layer = self._safe_text(validation.get("producer_layer"))
            if producer_layer == "step_executor":
                return "step_executor_execution_evidence"
            return "governed_execution_evidence"
        if isinstance(value, dict):
            evidence_type = self._safe_text(value.get("evidence_type"))
            producer_layer = self._safe_text(value.get("producer_layer"))
            record_type = self._safe_text(value.get("record_type"))
            if evidence_type == "output_artifact" or producer_layer == "output_artifact":
                return "output_artifact"
            if evidence_type or producer_layer or record_type:
                return "external_imported_record"
        return "invalid_record"

    def _invalid_record_reasons(self, name: str, value: Any) -> list[str]:
        if value is None or self._valid_record(name, value):
            return []
        return self._external_record_validation(name, value)["reasons"]

    def _external_record_validation(self, name: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {
                "accepted": False,
                "producer_layer": "",
                "reasons": ["unsupported_record_type"],
            }

        reasons: list[str] = []
        record_type = self._safe_text(value.get("record_type"))
        expected_record_type = EXTERNAL_RECORD_TYPES.get(name, "")
        if not record_type:
            reasons.append("missing_record_type")
        elif record_type != expected_record_type:
            reasons.append("record_type_mismatch")

        evidence_type = self._safe_text(value.get("evidence_type"))
        if not evidence_type:
            reasons.append("missing_evidence_type")
        elif evidence_type != "governed_runtime_evidence":
            reasons.append("unsupported_evidence_type")

        producer_layer = self._safe_text(value.get("producer_layer"))
        if not producer_layer:
            reasons.append("missing_producer_layer")
        elif producer_layer not in SEAL_ACCEPTED_PRODUCER_LAYERS:
            reasons.append("unknown_or_untrusted_producer_layer")

        if not self._has_provenance(value):
            reasons.append("missing_provenance")

        if value.get("normalized") is not True:
            reasons.append("not_normalized")

        validation = self._safe_mapping(value.get("validation") or value.get("seal_validation"))
        if validation.get("validated") is not True:
            reasons.append("not_validated")
        if validation.get("provenance_checked") is not True:
            reasons.append("provenance_not_checked")
        if validation.get("seal_valid") is not True:
            reasons.append("seal_not_validated")

        return {
            "accepted": not reasons,
            "producer_layer": producer_layer,
            "reasons": reasons,
        }

    def _has_provenance(self, value: dict[str, Any]) -> bool:
        provenance = value.get("provenance")
        if isinstance(provenance, dict):
            return bool(self._safe_text(provenance.get("source") or provenance.get("source_uri")))
        return bool(self._safe_text(value.get("source") or value.get("source_uri")))

    def _record_field(self, record: Any, field_name: str) -> Any:
        if isinstance(record, dict):
            return record.get(field_name, "")
        return getattr(record, field_name, "")

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
