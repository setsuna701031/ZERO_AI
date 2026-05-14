from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery


class RuntimeEvidenceRegistrySnapshot:
    SCHEMA = "zero.runtime_evidence.registry_snapshot.v1"

    def __init__(self, registry_payload: dict[str, Any]) -> None:
        self._payload = copy.deepcopy(registry_payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return self._payload.get("fingerprint", "")

    def lookup_execution(self, execution_id: str) -> dict[str, Any]:
        return self._lookup("execution_index", execution_id, "execution_id")

    def lookup_step(self, step_id: str) -> dict[str, Any]:
        return self._lookup("step_index", step_id, "step_id")

    def lookup_lineage(self, lineage_id: str) -> dict[str, Any]:
        return self._lookup("lineage_index", lineage_id, "lineage_id")

    def lookup_replay(self, replay_id: str) -> dict[str, Any]:
        return self._lookup("replay_index", replay_id, "replay_id")

    def lookup_rollback(self, rollback_id: str) -> dict[str, Any]:
        return self._lookup("rollback_index", rollback_id, "rollback_id")

    def sealed_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("sealed_state", {}))

    def failed_executions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("failed_execution_index", []))

    def _lookup(self, index_name: str, lookup_id: str, id_field: str) -> dict[str, Any]:
        lookup_id = "" if lookup_id is None else str(lookup_id)
        index = self._payload.get(index_name)
        if not isinstance(index, dict):
            index = {}
        value = index.get(lookup_id)
        if isinstance(value, dict):
            result = copy.deepcopy(value)
            result["found"] = True
            return result
        return {
            "found": False,
            id_field: lookup_id,
        }


class RuntimeEvidenceRegistry:
    """Read-only rebuildable indexes over runtime evidence query results."""

    def __init__(self, query: RuntimeEvidenceQuery | None = None) -> None:
        self.query = query if query is not None else RuntimeEvidenceQuery()

    def rebuild(self, source: Any) -> RuntimeEvidenceRegistrySnapshot:
        summary = self.query.summary_from(source)
        sealed_state = self.query.sealed_state(summary)
        replay_lineage = self.query.replay_lineage(summary)
        rollback_linkage = self.query.rollback_linkage(summary)
        failed = self.query.failed_steps(summary)
        events = self.query.filter_events(summary)

        execution_order = self._safe_text_list(summary.get("execution_order"))
        execution_index = self._build_execution_index(summary, execution_order)
        step_index = self._build_step_index(summary, execution_order, events.get("events", []))
        lineage_index = self._build_lineage_index(replay_lineage)
        replay_index = self._build_replay_index(summary, replay_lineage)
        rollback_index = self._build_rollback_index(rollback_linkage)
        failed_execution_index = self._build_failed_execution_index(failed)

        payload = {
            "ok": True,
            "schema": RuntimeEvidenceRegistrySnapshot.SCHEMA,
            "sealed": bool(sealed_state.get("sealed", False)),
            "sealed_state": self._without_fingerprint(sealed_state),
            "summary_fingerprint": self._safe_text(summary.get("summary_fingerprint")),
            "record_refs": self._safe_mapping(summary.get("record_refs")),
            "execution_index": execution_index,
            "step_index": step_index,
            "lineage_index": lineage_index,
            "replay_index": replay_index,
            "rollback_index": rollback_index,
            "failed_execution_index": failed_execution_index,
            "event_index": self._build_event_index(events.get("events", [])),
            "index_counts": {
                "executions": len(execution_index),
                "steps": len(step_index),
                "lineage": len(lineage_index),
                "replay": len(replay_index),
                "rollback": len(rollback_index),
                "failed_executions": len(failed_execution_index),
                "events": self._safe_int(events.get("count"), 0),
            },
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeEvidenceRegistrySnapshot(payload)

    def _build_execution_index(
        self,
        summary: dict[str, Any],
        execution_order: list[str],
    ) -> dict[str, dict[str, Any]]:
        aggregate_status = self._safe_text(summary.get("aggregate_status"))
        refs = self._safe_mapping(summary.get("record_refs"))
        return {
            operation_id: {
                "execution_id": operation_id,
                "execution_index": index,
                "aggregate_status": aggregate_status,
                "record_refs": copy.deepcopy(refs),
            }
            for index, operation_id in enumerate(execution_order)
        }

    def _build_step_index(
        self,
        summary: dict[str, Any],
        execution_order: list[str],
        events: Any,
    ) -> dict[str, dict[str, Any]]:
        step_index = {
            operation_id: {
                "step_id": operation_id,
                "execution_id": operation_id,
                "execution_index": index,
                "step_kind": self._step_kind(operation_id),
                "aggregate_status": self._safe_text(summary.get("aggregate_status")),
            }
            for index, operation_id in enumerate(execution_order)
        }
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            if event.get("layer") != "step_executor":
                continue
            fingerprint = self._safe_text(event.get("fingerprint"))
            if not fingerprint:
                continue
            step_index.setdefault(
                fingerprint,
                {
                    "step_id": fingerprint,
                    "execution_id": "",
                    "execution_index": None,
                    "step_kind": "step_executor_event",
                    "event": copy.deepcopy(event),
                },
            )
        return step_index

    def _build_lineage_index(self, replay_lineage: dict[str, Any]) -> dict[str, dict[str, Any]]:
        lineage = replay_lineage.get("lineage")
        if not isinstance(lineage, list):
            lineage = []
        return {
            self._safe_text(node.get("id")): {
                "lineage_id": self._safe_text(node.get("id")),
                "lineage_type": self._safe_text(node.get("type")),
                "lineage_index": index,
                "verified": bool(replay_lineage.get("verified", False)),
            }
            for index, node in enumerate(lineage)
            if isinstance(node, dict) and self._safe_text(node.get("id"))
        }

    def _build_replay_index(
        self,
        summary: dict[str, Any],
        replay_lineage: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        refs = self._safe_mapping(summary.get("record_refs"))
        replay_id = self._safe_text(refs.get("replay_id"))
        if not replay_id:
            return {}
        return {
            replay_id: {
                "replay_id": replay_id,
                "snapshot_id": self._safe_text(refs.get("snapshot_id")),
                "audit_id": self._safe_text(refs.get("audit_id")),
                "bundle_id": self._safe_text(refs.get("bundle_id")),
                "verified": bool(replay_lineage.get("verified", False)),
                "lineage_ids": self._safe_text_list(replay_lineage.get("lineage_ids")),
            }
        }

    def _build_rollback_index(self, rollback_linkage: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rollback_id = self._safe_text(rollback_linkage.get("rollback_id"))
        if not rollback_id:
            return {}
        return {
            rollback_id: {
                "rollback_id": rollback_id,
                "snapshot_id": self._safe_text(rollback_linkage.get("snapshot_id")),
                "bundle_id": self._safe_text(rollback_linkage.get("bundle_id")),
                "verified": bool(rollback_linkage.get("verified", False)),
                "rollback_order": self._safe_text_list(rollback_linkage.get("rollback_order")),
                "rollback_step_count": self._safe_int(rollback_linkage.get("rollback_step_count"), 0),
            }
        }

    def _build_failed_execution_index(self, failed: dict[str, Any]) -> list[dict[str, Any]]:
        failed_steps = failed.get("failed_steps")
        if not isinstance(failed_steps, list):
            return []
        return [
            {
                "failed_execution_id": self._failed_execution_id(item, index),
                "source": self._safe_text(item.get("source")),
                "event_index": item.get("event_index"),
                "phase": self._safe_text(item.get("phase")),
                "status": self._safe_text(item.get("status")),
                "fingerprint": self._safe_text(item.get("fingerprint")),
            }
            for index, item in enumerate(failed_steps)
            if isinstance(item, dict)
        ]

    def _build_event_index(self, events: Any) -> list[dict[str, Any]]:
        if not isinstance(events, list):
            return []
        return [
            {
                "event_key": self._event_key(event, index),
                "layer": self._safe_text(event.get("layer")),
                "event_index": event.get("event_index"),
                "phase": self._safe_text(event.get("phase")),
                "status": self._safe_text(event.get("status")),
                "fingerprint": self._safe_text(event.get("fingerprint")),
            }
            for index, event in enumerate(events)
            if isinstance(event, dict)
        ]

    def _without_fingerprint(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe = self._safe_mapping(payload)
        safe.pop("summary_fingerprint", None)
        return safe

    def _failed_execution_id(self, item: dict[str, Any], index: int) -> str:
        fingerprint = self._safe_text(item.get("fingerprint"))
        if fingerprint:
            return fingerprint
        return f"{self._safe_text(item.get('source'))}:{index}"

    def _event_key(self, event: dict[str, Any], index: int) -> str:
        fingerprint = self._safe_text(event.get("fingerprint"))
        if fingerprint:
            return fingerprint
        return f"{self._safe_text(event.get('layer'))}:{self._safe_text(event.get('phase'))}:{index}"

    def _step_kind(self, step_id: str) -> str:
        if step_id.startswith("step_executor."):
            return "step_executor"
        if step_id.startswith("task_runtime."):
            return "task_runtime"
        if step_id.startswith("scheduler."):
            return "scheduler"
        return "unknown"

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_text_list(self, value: Any) -> list[str]:
        return [self._safe_text(item) for item in value] if isinstance(value, list) else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_runtime_evidence_registry(source: Any) -> RuntimeEvidenceRegistrySnapshot:
    return RuntimeEvidenceRegistry().rebuild(source)


__all__ = [
    "RuntimeEvidenceRegistry",
    "RuntimeEvidenceRegistrySnapshot",
    "build_runtime_evidence_registry",
]
