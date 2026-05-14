from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer


FAILED_STATUSES = {"failed", "error", "exception", "blocked", "denied"}


class RuntimeEvidenceQuery:
    """Composable read-only queries over runtime evidence consumer summaries."""

    SCHEMA = "zero.runtime_evidence.query_result.v1"

    def __init__(self, consumer: RuntimeEvidenceConsumer | None = None) -> None:
        self.consumer = consumer if consumer is not None else RuntimeEvidenceConsumer()

    def summary_from(self, source: Any) -> dict[str, Any]:
        if self._looks_like_summary(source):
            return self._copy(source)
        return self.consumer.read_seal(source)

    def sealed_state(self, source: Any) -> dict[str, Any]:
        summary = self.summary_from(source)
        missing = self._safe_list(summary.get("missing_records"))
        sealed = bool(summary.get("ok")) and not missing
        reason = ""
        if not sealed:
            reason = "missing_evidence" if missing else "unsealed"
        return self._result(
            "sealed_state",
            {
                "sealed": sealed,
                "complete": not missing,
                "reason": reason,
                "missing_records": missing,
                "record_count": self._safe_int(summary.get("record_count"), 0),
                "seal_id": self._safe_text(summary.get("seal_id")),
                "seal_fingerprint": self._safe_text(summary.get("seal_fingerprint")),
            },
        )

    def lookup_execution(self, source: Any, execution_id: str) -> dict[str, Any]:
        summary = self.summary_from(source)
        execution_id = self._safe_text(execution_id).strip()
        order = self._safe_text_list(summary.get("execution_order"))
        if not execution_id:
            return self._missing_result("execution", execution_id)

        for index, operation_id in enumerate(order):
            if operation_id == execution_id:
                return self._result(
                    "execution_lookup",
                    {
                        "found": True,
                        "operation_id": operation_id,
                        "execution_index": index,
                        "aggregate_status": self._safe_text(summary.get("aggregate_status")),
                        "record_refs": self._safe_mapping(summary.get("record_refs")),
                    },
                )
        return self._missing_result("execution", execution_id)

    def lookup_step(self, source: Any, step_id: str) -> dict[str, Any]:
        summary = self.summary_from(source)
        step_id = self._safe_text(step_id).strip()
        execution = self.lookup_execution(summary, step_id)
        if execution.get("found"):
            payload = self._safe_mapping(execution)
            payload["query_type"] = "step_lookup"
            payload["step_id"] = step_id
            payload["step_kind"] = self._step_kind(step_id)
            payload["summary_fingerprint"] = self._fingerprint(payload)
            return payload

        step_events = self.filter_events(summary, layer="step_executor")
        matched_events = [
            event
            for event in step_events.get("events", [])
            if step_id and step_id in self._safe_text(event.get("fingerprint"))
        ]
        return self._result(
            "step_lookup",
            {
                "found": bool(matched_events),
                "step_id": step_id,
                "step_kind": self._step_kind(step_id),
                "events": matched_events,
            },
        )

    def failed_steps(self, source: Any) -> dict[str, Any]:
        summary = self.summary_from(source)
        events = self.filter_events(summary, layer="step_executor").get("events", [])
        failed = [
            {
                "source": "step_executor_event",
                "event_index": event.get("event_index"),
                "phase": event.get("phase"),
                "status": event.get("status"),
                "fingerprint": event.get("fingerprint"),
            }
            for event in events
            if self._safe_text(event.get("status")).lower() in FAILED_STATUSES
        ]

        aggregate_status = self._safe_text(summary.get("aggregate_status")).lower()
        if not failed and aggregate_status in FAILED_STATUSES:
            failed.append(
                {
                    "source": "aggregate_status",
                    "event_index": None,
                    "phase": "",
                    "status": aggregate_status,
                    "fingerprint": "",
                }
            )

        return self._result(
            "failed_steps",
            {
                "failed": bool(failed),
                "failed_steps": failed,
                "failed_step_count": len(failed),
            },
        )

    def replay_lineage(self, source: Any) -> dict[str, Any]:
        summary = self.summary_from(source)
        refs = self._safe_mapping(summary.get("record_refs"))
        lineage = [
            self._lineage_node("plan", refs.get("plan_id")),
            self._lineage_node("snapshot", refs.get("snapshot_id")),
            self._lineage_node("replay", refs.get("replay_id")),
            self._lineage_node("audit", refs.get("audit_id")),
            self._lineage_node("bundle", refs.get("bundle_id")),
        ]
        lineage = [node for node in lineage if node["id"]]
        return self._result(
            "replay_lineage",
            {
                "found": bool(lineage),
                "verified": self._safe_mapping(summary.get("verification")).get("replay") == "verified",
                "lineage": lineage,
                "lineage_ids": [node["id"] for node in lineage],
            },
        )

    def rollback_linkage(self, source: Any) -> dict[str, Any]:
        summary = self.summary_from(source)
        refs = self._safe_mapping(summary.get("record_refs"))
        rollback_order = self._safe_text_list(summary.get("rollback_order"))
        return self._result(
            "rollback_linkage",
            {
                "found": bool(refs.get("rollback_id")),
                "verified": self._safe_mapping(summary.get("verification")).get("rollback") == "verified",
                "rollback_id": self._safe_text(refs.get("rollback_id")),
                "snapshot_id": self._safe_text(refs.get("snapshot_id")),
                "bundle_id": self._safe_text(refs.get("bundle_id")),
                "rollback_order": rollback_order,
                "rollback_step_count": len(rollback_order),
            },
        )

    def filter_events(
        self,
        source: Any,
        *,
        layer: str | None = None,
        phase: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        summary = self.summary_from(source)
        layer_filter = self._safe_text(layer).strip()
        phase_filter = self._safe_text(phase).strip()
        status_filter = self._safe_text(status).strip()
        layers = self._safe_mapping(summary.get("events"))
        selected_layers = [layer_filter] if layer_filter else sorted(layers)

        events: list[dict[str, Any]] = []
        for current_layer in selected_layers:
            event_summary = self._safe_mapping(layers.get(current_layer))
            phases = self._safe_text_list(event_summary.get("phases"))
            statuses = self._safe_text_list(event_summary.get("statuses"))
            fingerprints = self._safe_text_list(event_summary.get("fingerprints"))
            count = max(len(phases), len(statuses), len(fingerprints))
            for index in range(count):
                event = {
                    "layer": current_layer,
                    "event_index": index,
                    "phase": phases[index] if index < len(phases) else "",
                    "status": statuses[index] if index < len(statuses) else "",
                    "fingerprint": fingerprints[index] if index < len(fingerprints) else "",
                }
                if phase_filter and event["phase"] != phase_filter:
                    continue
                if status_filter and event["status"] != status_filter:
                    continue
                events.append(event)

        return self._result(
            "event_filter",
            {
                "count": len(events),
                "events": events,
            },
        )

    def _missing_result(self, kind: str, lookup_id: str) -> dict[str, Any]:
        return self._result(
            f"{kind}_lookup",
            {
                "found": False,
                f"{kind}_id": self._safe_text(lookup_id),
            },
        )

    def _result(self, query_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = {
            "ok": True,
            "schema": self.SCHEMA,
            "query_type": query_type,
            **self._copy(payload),
        }
        result["summary_fingerprint"] = self._fingerprint(result)
        return self._copy(result)

    def _lineage_node(self, node_type: str, node_id: Any) -> dict[str, str]:
        return {
            "type": node_type,
            "id": self._safe_text(node_id),
        }

    def _step_kind(self, step_id: str) -> str:
        if step_id.startswith("step_executor."):
            return "step_executor"
        if step_id.startswith("task_runtime."):
            return "task_runtime"
        if step_id.startswith("scheduler."):
            return "scheduler"
        return "unknown"

    def _looks_like_summary(self, source: Any) -> bool:
        return isinstance(source, dict) and source.get("schema") == RuntimeEvidenceConsumer.SCHEMA

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list[Any]:
        return copy.deepcopy(value) if isinstance(value, list) else []

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
        safe = self._copy(payload)
        safe.pop("summary_fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _copy(self, value: Any) -> Any:
        return copy.deepcopy(value)


def query_runtime_evidence(source: Any, query: str, **kwargs: Any) -> dict[str, Any]:
    runtime_query = RuntimeEvidenceQuery()
    if query == "sealed_state":
        return runtime_query.sealed_state(source)
    if query == "execution":
        return runtime_query.lookup_execution(source, kwargs.get("execution_id", ""))
    if query == "step":
        return runtime_query.lookup_step(source, kwargs.get("step_id", ""))
    if query == "failed_steps":
        return runtime_query.failed_steps(source)
    if query == "replay_lineage":
        return runtime_query.replay_lineage(source)
    if query == "rollback_linkage":
        return runtime_query.rollback_linkage(source)
    if query == "events":
        return runtime_query.filter_events(
            source,
            layer=kwargs.get("layer"),
            phase=kwargs.get("phase"),
            status=kwargs.get("status"),
        )
    return {
        "ok": False,
        "schema": RuntimeEvidenceQuery.SCHEMA,
        "query_type": "" if query is None else str(query),
        "error": "unknown runtime evidence query",
    }


__all__ = [
    "RuntimeEvidenceQuery",
    "query_runtime_evidence",
]
