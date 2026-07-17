from __future__ import annotations

"""Read-only decision evidence projection for control-layer inspection."""

import copy
import json
from pathlib import Path
from typing import Any, Mapping


UNAVAILABLE = "unavailable"


def _text(value: Any, default: str = UNAVAILABLE) -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return [copy.deepcopy(dict(item)) for item in records if isinstance(item, Mapping)]


def _format_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return UNAVAILABLE
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _record_sort_key(record: Mapping[str, Any]) -> tuple[float, str]:
    try:
        created_at = float(record.get("created_at") or 0)
    except (TypeError, ValueError):
        created_at = 0.0
    return created_at, _text(record.get("decision_id"), "")


def _view_record(record: Mapping[str, Any]) -> dict[str, Any]:
    links = _mapping(record.get("links"))
    return {
        "decision_id": _text(record.get("decision_id")),
        "goal_id": _text(record.get("goal_id")),
        "task_id": _text(record.get("task_id")),
        "source_stage": _text(record.get("source_stage")),
        "created_at": record.get("created_at", UNAVAILABLE),
        "timeline": {
            "observed_event": copy.deepcopy(record.get("observed_event"))
            if record.get("observed_event") not in (None, "", [], {})
            else UNAVAILABLE,
            "outcome_class": _text(record.get("outcome_class")),
            "decision": _text(record.get("decision")),
            "reason": _text(record.get("decision_reason")),
            "next_action": _text(record.get("next_action")),
        },
        "links": {
            "cycle_index": links.get("cycle_index", UNAVAILABLE),
            "continuation_goal_id": _text(links.get("continuation_goal_id")),
            "replan_goal_id": _text(links.get("replan_goal_id")),
        },
        "evidence_refs": copy.deepcopy(record.get("evidence_refs"))
        if isinstance(record.get("evidence_refs"), list)
        else [],
    }


class DecisionEvidenceViewer:
    """Read existing decision evidence without mutating or executing anything."""

    def __init__(self, repo_root: str | Path, *, storage_path: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = (
            Path(storage_path)
            if storage_path is not None
            else self.repo_root / "runtime" / "evidence" / "decision_evidence.json"
        )
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    def load_records(self) -> list[dict[str, Any]]:
        if not self.storage_path.is_file():
            return []
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return sorted(_records_from_payload(payload), key=_record_sort_key)

    def view(self, *, goal_id: str = "", task_id: str = "") -> dict[str, Any]:
        normalized_goal_id = str(goal_id or "").strip()
        normalized_task_id = str(task_id or "").strip()
        records = self.load_records()
        if normalized_goal_id:
            records = [record for record in records if _text(record.get("goal_id"), "") == normalized_goal_id]
        if normalized_task_id:
            records = [record for record in records if _text(record.get("task_id"), "") == normalized_task_id]
        return {
            "ok": True,
            "mode": "decision_evidence_viewer",
            "store_path": str(self.storage_path),
            "filters": {
                "goal_id": normalized_goal_id or UNAVAILABLE,
                "task_id": normalized_task_id or UNAVAILABLE,
            },
            "record_count": len(records),
            "records": [_view_record(record) for record in records],
        }

    def render_text(self, *, goal_id: str = "", task_id: str = "") -> str:
        view = self.view(goal_id=goal_id, task_id=task_id)
        lines = [
            "Decision Evidence",
            f"store: {view['store_path']}",
            f"filters: goal_id={view['filters']['goal_id']} task_id={view['filters']['task_id']}",
            f"records: {view['record_count']}",
        ]
        if not view["records"]:
            lines.append("No decision evidence records matched.")
            return "\n".join(lines)

        for index, record in enumerate(view["records"], start=1):
            timeline = record["timeline"]
            links = record["links"]
            lines.extend(
                [
                    "",
                    f"{index}. {record['decision_id']}",
                    f"   goal_id: {record['goal_id']}",
                    f"   task_id: {record['task_id']}",
                    f"   source_stage: {record['source_stage']}",
                    "   timeline:",
                    f"     observed_event: {_format_value(timeline['observed_event'])}",
                    f"     outcome_class: {timeline['outcome_class']}",
                    f"     decision: {timeline['decision']}",
                    f"     reason: {timeline['reason']}",
                    f"     next_action: {timeline['next_action']}",
                    "   GoalLoop links:",
                    f"     cycle_index: {_format_value(links['cycle_index'])}",
                    f"     continuation_goal_id: {links['continuation_goal_id']}",
                    f"     replan_goal_id: {links['replan_goal_id']}",
                    f"   evidence_refs: {_format_value(record['evidence_refs'])}",
                ]
            )
        return "\n".join(lines)


__all__ = ["DecisionEvidenceViewer", "UNAVAILABLE"]
