from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Mapping

from core.runtime.aer_operator_lifecycle import OPERATOR_PHASES, normalize_operator_phase

AER_OPERATOR_EVENT_CONTRACT = "aer.operator_event.v2"

OPERATOR_EVENT_LOG_DIR_NAME = "operator_events"
OPERATOR_EVENT_LOG_FILE_NAME = "events.jsonl"

OPERATOR_EVENT_REQUIRED_FIELDS = (
    "contract",
    "event_id",
    "operator_session_id",
    "package_id",
    "event_type",
    "phase",
    "message",
    "metadata",
    "sequence",
)


def operator_event_log_dir(workspace_root: str) -> str:
    return os.path.abspath(os.path.join(str(workspace_root or ""), OPERATOR_EVENT_LOG_DIR_NAME))


def operator_event_log_path(workspace_root: str) -> str:
    log_dir = operator_event_log_dir(workspace_root)
    path = os.path.abspath(os.path.join(log_dir, OPERATOR_EVENT_LOG_FILE_NAME))
    _ensure_inside_event_log_dir(log_dir, path)
    return path


def build_operator_event(
    *,
    event_id: str,
    operator_session_id: str,
    package_id: str,
    event_type: str,
    phase: str = "initialized",
    message: str = "",
    metadata: Mapping[str, Any] | None = None,
    sequence: int = 0,
) -> Dict[str, Any]:
    return {
        "contract": AER_OPERATOR_EVENT_CONTRACT,
        "event_id": str(event_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "event_type": str(event_type or ""),
        "phase": normalize_operator_phase(phase),
        "message": str(message or ""),
        "metadata": copy.deepcopy(dict(metadata or {})),
        "sequence": int(sequence or 0),
    }


def validate_operator_event(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_EVENT_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    for field in OPERATOR_EVENT_REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_EVENT_CONTRACT:
        errors.append("invalid contract")

    for field in ("event_id", "operator_session_id", "package_id", "event_type"):
        if not str(payload.get(field) or "").strip():
            errors.append(f"{field} is required")

    phase = payload.get("phase")
    if phase not in OPERATOR_PHASES:
        errors.append(f"invalid phase: {phase}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    try:
        sequence = int(payload.get("sequence"))
        if sequence < 0:
            errors.append("sequence must be >= 0")
    except Exception:
        errors.append("sequence must be an int")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_EVENT_CONTRACT,
        "errors": errors,
    }


def append_operator_event(workspace_root: str, event: dict) -> dict:
    validation = validate_operator_event(event)
    if validation["ok"] is not True:
        return _result(False, "append_operator_event", errors=list(validation["errors"]))

    log_dir = operator_event_log_dir(workspace_root)
    path = operator_event_log_path(workspace_root)
    sequence_validation = _validate_append_sequence(path, int(event.get("sequence")))
    if sequence_validation["ok"] is not True:
        return _result(False, "append_operator_event", errors=list(sequence_validation["errors"]))

    os.makedirs(log_dir, exist_ok=True)

    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_stable_json(event))
        handle.write("\n")

    return _result(
        True,
        "append_operator_event",
        event_id=str(event.get("event_id") or ""),
        path=path,
    )


def load_operator_events(
    workspace_root: str,
    operator_session_id: str | None = None,
    package_id: str | None = None,
) -> List[dict]:
    path = operator_event_log_path(workspace_root)
    if not os.path.exists(path):
        return []

    session_filter = str(operator_session_id or "")
    package_filter = str(package_id or "")
    records: List[dict] = []

    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception as exc:
                records.append(
                    _result(
                        False,
                        "load_operator_events",
                        path=path,
                        errors=[f"invalid event log line {line_number}: {exc}"],
                    )
                )
                continue

            validation = validate_operator_event(payload)
            if validation["ok"] is not True:
                records.append(
                    _result(
                        False,
                        "load_operator_events",
                        event_id=str(payload.get("event_id") or "") if isinstance(payload, dict) else "",
                        path=path,
                        errors=list(validation["errors"]),
                    )
                )
                continue

            if session_filter and payload.get("operator_session_id") != session_filter:
                continue
            if package_filter and payload.get("package_id") != package_filter:
                continue
            records.append(payload)

    return records


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ensure_inside_event_log_dir(log_dir: str, path: str) -> None:
    root = os.path.abspath(log_dir)
    target = os.path.abspath(path)
    try:
        common = os.path.commonpath([root, target])
    except ValueError as exc:
        raise ValueError("operator event log path must stay inside event log directory") from exc
    if common != root:
        raise ValueError("operator event log path must stay inside event log directory")


def _validate_append_sequence(path: str, sequence: int) -> dict:
    if not os.path.exists(path):
        return _result(True, "validate_append_sequence")

    last_sequence: int | None = None
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            validation = validate_operator_event(payload)
            if validation["ok"] is True:
                last_sequence = int(payload.get("sequence"))

    if last_sequence is not None and sequence < last_sequence:
        return _result(
            False,
            "validate_append_sequence",
            errors=[f"sequence must be monotonically increasing: {sequence} < {last_sequence}"],
        )
    return _result(True, "validate_append_sequence")


def _result(
    ok: bool,
    action: str,
    *,
    event_id: str = "",
    path: str = "",
    errors: List[str] | None = None,
) -> dict:
    return {
        "ok": ok,
        "action": action,
        "event_id": event_id,
        "path": path,
        "errors": list(errors or []),
    }
