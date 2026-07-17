from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_goal_executor import (
    REQUEST_CONTRACT as GOAL_EXECUTION_REQUEST_CONTRACT,
    create_goal_execution_request,
)
from core.runtime.runtime_operator_session import fingerprint, time_text

CONTRACT = "zero.runtime.goal_execution_registry.v1"
ENTRY_CONTRACT = "zero.runtime.goal_execution_registry_entry.v1"

SUPPORTED_GOAL_TYPES = {
    "inspect",
    "document",
    "modify",
    "validate",
}

FORBIDDEN_EXECUTABLE_FIELDS = {
    "argv",
    "callable",
    "command",
    "dynamic_import",
    "eval",
    "exec",
    "network",
    "shell",
    "subprocess",
}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        text = str(item or "").strip().replace("\\", "/")
        if text and text not in result:
            result.append(text)
    return result


def _unsafe(path: Path) -> bool:
    try:
        attributes = getattr(
            path.lstat(),
            "st_file_attributes",
            0,
        )
        reparse_flag = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        return path.is_symlink() or bool(
            attributes & reparse_flag
        )
    except OSError:
        return False


def _unsigned_registry(
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(registry)
    value.pop("registry_fingerprint", None)
    return value


def _unsigned_entry(
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(entry)
    value.pop("entry_fingerprint", None)
    return value


def seal_registry_entry(
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned_entry(entry)
    value["entry_fingerprint"] = fingerprint(value)
    return value


def seal_goal_execution_registry(
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned_registry(registry)
    value["registry_fingerprint"] = fingerprint(value)
    return value


def create_goal_execution_registry(
    *,
    registry_id: str,
    now: Any = None,
) -> dict[str, Any]:
    identity = str(registry_id or "").strip()
    if not identity:
        raise ValueError("registry_id_required")

    return seal_goal_execution_registry(
        {
            "contract": CONTRACT,
            "registry_id": identity,
            "registry_status": "active",
            "created_at": time_text(now),
            "updated_at": time_text(now),
            "entries": {},
            "entry_order": [],
            "entry_count": 0,
            "audit_record": {
                "event_type": (
                    "runtime_goal_execution_registry_created"
                ),
                "created_at": time_text(now),
            },
        }
    )


def _normalize_goal(
    mission: Mapping[str, Any],
    goal: Mapping[str, Any],
) -> dict[str, Any]:
    mission_value = _mapping(mission)
    goal_value = _mapping(goal)

    mission_id = str(
        goal_value.get("mission_id")
        or mission_value.get("mission_id")
        or ""
    ).strip()
    goal_id = str(
        goal_value.get("goal_id")
        or ""
    ).strip()
    goal_type = str(
        goal_value.get("goal_type")
        or goal_value.get("type")
        or ""
    ).strip().lower()

    approved_scope = _string_list(
        goal_value.get("target_scope")
        or goal_value.get("approved_target_scope")
        or []
    )
    excluded_scope = _string_list(
        goal_value.get("excluded_scope")
        or _mapping(
            mission_value.get("planner_output_summary")
        ).get("excluded_scope")
        or []
    )

    authoring_instruction = _mapping(
        goal_value.get("authoring_instruction")
    )
    operator_context = _mapping(
        goal_value.get("operator_context")
    )

    if authoring_instruction:
        operator_context.setdefault(
            "authoring_instruction",
            authoring_instruction,
        )

    normalized = {
        "mission_id": mission_id,
        "goal_id": goal_id,
        "goal_type": goal_type,
        "goal_title": str(
            goal_value.get("goal_title")
            or ""
        ).strip(),
        "goal_description": str(
            goal_value.get("goal_description")
            or goal_value.get("description")
            or ""
        ).strip(),
        "target_scope": approved_scope,
        "excluded_scope": excluded_scope,
        "acceptance_criteria": deepcopy(
            goal_value.get("acceptance_criteria")
            or []
        ),
        "validation_requirements": deepcopy(
            goal_value.get("validation_requirements")
            or []
        ),
        "operator_context": operator_context,
        "goal_fingerprint": str(
            goal_value.get("goal_fingerprint")
            or ""
        ).strip(),
    }

    if not normalized["goal_fingerprint"]:
        normalized["goal_fingerprint"] = fingerprint(
            {
                key: deepcopy(value)
                for key, value in normalized.items()
                if key != "goal_fingerprint"
            }
        )

    return normalized


def validate_registry_entry(
    entry: Mapping[str, Any],
) -> list[str]:
    value = _mapping(entry)
    reasons: list[str] = []

    if value.get("contract") != ENTRY_CONTRACT:
        reasons.append("invalid_registry_entry_contract")

    if value.get("entry_fingerprint") != fingerprint(
        _unsigned_entry(value)
    ):
        reasons.append("registry_entry_fingerprint_mismatch")

    for field in (
        "entry_id",
        "registry_id",
        "mission_id",
        "goal_id",
        "session_id",
        "execution_request_fingerprint",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("entry_status") not in {
        "registered",
        "consumed",
        "invalidated",
    }:
        reasons.append("invalid_registry_entry_status")

    request = _mapping(value.get("execution_request"))
    if request.get("contract") != (
        GOAL_EXECUTION_REQUEST_CONTRACT
    ):
        reasons.append("invalid_execution_request_contract")

    if request.get("session_id") != value.get("session_id"):
        reasons.append("registry_request_session_mismatch")

    if request.get("goal_id") != value.get("goal_id"):
        reasons.append("registry_request_goal_mismatch")

    if request.get("mission_id") != value.get("mission_id"):
        reasons.append("registry_request_mission_mismatch")

    if request.get("execution_request_fingerprint") != (
        value.get("execution_request_fingerprint")
    ):
        reasons.append(
            "registry_request_fingerprint_mismatch"
        )

    if value.get("workspace_mutated") is not False:
        reasons.append("registry_must_not_mutate_workspace")

    if value.get("transaction_invoked") is not False:
        reasons.append("registry_must_not_invoke_transaction")

    return sorted(set(reasons))


def validate_goal_execution_registry(
    registry: Mapping[str, Any],
) -> list[str]:
    value = _mapping(registry)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append(
            "invalid_goal_execution_registry_contract"
        )

    if value.get("registry_fingerprint") != fingerprint(
        _unsigned_registry(value)
    ):
        reasons.append(
            "goal_execution_registry_fingerprint_mismatch"
        )

    if not str(value.get("registry_id") or "").strip():
        reasons.append("registry_id_required")

    if value.get("registry_status") not in {
        "active",
        "closed",
    }:
        reasons.append("invalid_registry_status")

    entries = _mapping(value.get("entries"))
    order = value.get("entry_order")

    if not isinstance(order, list):
        reasons.append("entry_order_must_be_list")
        order = []

    if list(entries) != order:
        reasons.append("registry_entry_order_mismatch")

    if value.get("entry_count") != len(entries):
        reasons.append("registry_entry_count_mismatch")

    for entry_id, entry in entries.items():
        entry_value = _mapping(entry)
        if entry_value.get("entry_id") != entry_id:
            reasons.append("registry_entry_identity_mismatch")
        reasons.extend(validate_registry_entry(entry_value))

    return sorted(set(reasons))


def register_goal_execution_request(
    registry: Mapping[str, Any],
    *,
    mission: Mapping[str, Any],
    goal: Mapping[str, Any],
    session: Mapping[str, Any],
    artifact_root: Any,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(registry)
    registry_reasons = validate_goal_execution_registry(value)
    if registry_reasons:
        raise ValueError(";".join(registry_reasons))

    if value.get("registry_status") != "active":
        raise ValueError("registry_not_active")

    normalized_goal = _normalize_goal(mission, goal)
    reasons: list[str] = []

    if not normalized_goal["mission_id"]:
        reasons.append("mission_id_required")

    if not normalized_goal["goal_id"]:
        reasons.append("goal_id_required")

    if normalized_goal["goal_type"] not in SUPPORTED_GOAL_TYPES:
        reasons.append("unsupported_goal_type")

    if not normalized_goal["target_scope"]:
        reasons.append("approved_scope_required")

    if set(normalized_goal["target_scope"]) & set(
        normalized_goal["excluded_scope"]
    ):
        reasons.append(
            "approved_scope_intersects_excluded_scope"
        )

    operator_context = _mapping(
        normalized_goal.get("operator_context")
    )
    if FORBIDDEN_EXECUTABLE_FIELDS & set(operator_context):
        reasons.append("executable_operator_context_forbidden")

    session_value = _mapping(session)
    session_id = str(
        session_value.get("session_id")
        or ""
    ).strip()
    if not session_id:
        reasons.append("session_id_required")

    if session_value.get("session_status") != (
        "waiting_for_candidate_bundle"
    ):
        reasons.append(
            "session_not_waiting_for_candidate_bundle"
        )

    if session_value.get("required_action") != (
        "candidate_bundle"
    ):
        reasons.append("candidate_bundle_action_not_required")

    artifact_root_text = str(
        artifact_root or ""
    ).strip()
    if not artifact_root_text:
        reasons.append("artifact_root_required")

    if reasons:
        raise ValueError(";".join(sorted(set(reasons))))

    request = create_goal_execution_request(
        normalized_goal,
        session_value,
        operator_context=operator_context,
        now=now,
    )

    entry_identity = {
        "registry_id": value["registry_id"],
        "mission_id": normalized_goal["mission_id"],
        "goal_id": normalized_goal["goal_id"],
        "session_id": session_id,
        "execution_request_fingerprint": request[
            "execution_request_fingerprint"
        ],
    }
    entry_id = (
        f"goal-execution-entry-"
        f"{fingerprint(entry_identity)[:20]}"
    )

    existing = _mapping(
        _mapping(value.get("entries")).get(entry_id)
    )
    if existing:
        if existing.get(
            "execution_request_fingerprint"
        ) != request.get(
            "execution_request_fingerprint"
        ):
            raise ValueError(
                "registry_entry_identity_collision"
            )
        return seal_goal_execution_registry(value)

    entry = seal_registry_entry(
        {
            "contract": ENTRY_CONTRACT,
            "entry_id": entry_id,
            "registry_id": value["registry_id"],
            "entry_status": "registered",
            "registered_at": time_text(now),
            "consumed_at": None,
            "invalidated_at": None,
            "mission_id": normalized_goal["mission_id"],
            "goal_id": normalized_goal["goal_id"],
            "goal_type": normalized_goal["goal_type"],
            "goal_fingerprint": normalized_goal[
                "goal_fingerprint"
            ],
            "session_id": session_id,
            "session_fingerprint": session_value.get(
                "session_fingerprint"
            ),
            "approved_scope": deepcopy(
                normalized_goal["target_scope"]
            ),
            "excluded_scope": deepcopy(
                normalized_goal["excluded_scope"]
            ),
            "artifact_root": artifact_root_text,
            "execution_request": request,
            "execution_request_fingerprint": request[
                "execution_request_fingerprint"
            ],
            "workspace_mutated": False,
            "transaction_invoked": False,
            "audit_record": {
                "event_type": (
                    "runtime_goal_execution_request_registered"
                ),
                "registered_at": time_text(now),
                "mission_id": normalized_goal["mission_id"],
                "goal_id": normalized_goal["goal_id"],
                "session_id": session_id,
            },
        }
    )

    entries = _mapping(value.get("entries"))
    entries[entry_id] = entry
    order = list(value.get("entry_order") or [])
    order.append(entry_id)

    value["entries"] = entries
    value["entry_order"] = order
    value["entry_count"] = len(entries)
    value["updated_at"] = time_text(now)

    sealed = seal_goal_execution_registry(value)
    validation_reasons = validate_goal_execution_registry(
        sealed
    )
    if validation_reasons:
        raise ValueError(";".join(validation_reasons))

    return sealed


def pending_goal_execution_requests(
    registry: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    value = _mapping(registry)
    reasons = validate_goal_execution_registry(value)
    if reasons:
        raise ValueError(";".join(reasons))

    result: dict[str, dict[str, Any]] = {}
    for entry_id in value.get("entry_order") or []:
        entry = _mapping(
            _mapping(value.get("entries")).get(entry_id)
        )
        if entry.get("entry_status") != "registered":
            continue

        session_id = str(
            entry.get("session_id")
            or ""
        ).strip()
        if not session_id:
            continue

        result[session_id] = {
            "goal": deepcopy(
                _mapping(
                    entry.get("execution_request")
                ).get("goal")
                or {
                    "goal_id": entry.get("goal_id"),
                    "mission_id": entry.get("mission_id"),
                    "goal_type": entry.get("goal_type"),
                    "goal_fingerprint": entry.get(
                        "goal_fingerprint"
                    ),
                    "target_scope": deepcopy(
                        entry.get("approved_scope") or []
                    ),
                    "excluded_scope": deepcopy(
                        entry.get("excluded_scope") or []
                    ),
                }
            ),
            "operator_context": deepcopy(
                _mapping(
                    entry.get("execution_request")
                ).get("operator_context")
                or {}
            ),
            "artifact_root": entry.get("artifact_root"),
            "registry_entry_id": entry_id,
            "execution_request": deepcopy(
                entry.get("execution_request")
            ),
            "execution_request_fingerprint": entry.get(
                "execution_request_fingerprint"
            ),
        }

    return result


def mark_registry_entry_consumed(
    registry: Mapping[str, Any],
    *,
    entry_id: str,
    execution_result_fingerprint: str,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(registry)
    reasons = validate_goal_execution_registry(value)
    if reasons:
        raise ValueError(";".join(reasons))

    identity = str(entry_id or "").strip()
    if identity not in _mapping(value.get("entries")):
        raise ValueError("unknown_registry_entry")

    result_fingerprint = str(
        execution_result_fingerprint or ""
    ).strip()
    if not result_fingerprint:
        raise ValueError(
            "execution_result_fingerprint_required"
        )

    entries = _mapping(value.get("entries"))
    entry = _mapping(entries[identity])

    if entry.get("entry_status") == "consumed":
        if entry.get(
            "execution_result_fingerprint"
        ) != result_fingerprint:
            raise ValueError(
                "registry_entry_consumption_mismatch"
            )
        return seal_goal_execution_registry(value)

    if entry.get("entry_status") != "registered":
        raise ValueError("registry_entry_not_consumable")

    entry["entry_status"] = "consumed"
    entry["consumed_at"] = time_text(now)
    entry["execution_result_fingerprint"] = (
        result_fingerprint
    )
    entries[identity] = seal_registry_entry(entry)

    value["entries"] = entries
    value["updated_at"] = time_text(now)
    return seal_goal_execution_registry(value)


def finalize_goal_execution_registry(
    registry: Mapping[str, Any],
    *,
    mission: Mapping[str, Any],
    sessions: Mapping[str, Mapping[str, Any]],
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(registry)
    reasons = validate_goal_execution_registry(value)
    if reasons:
        raise ValueError(";".join(reasons))
    if mission.get("mission_status") != "completed":
        raise ValueError("mission_not_completed")

    records = _mapping(value.get("completion_records"))
    entries = _mapping(value.get("entries"))
    for goal_id in mission.get("goal_order") or []:
        goal = _mapping(_mapping(mission.get("goals")).get(goal_id))
        if goal.get("goal_status") != "completed":
            raise ValueError("goal_not_completed")
        session = _mapping(sessions.get(goal_id))
        tx = _mapping(_mapping(session.get("artifacts")).get("transaction_result"))
        evidence = _mapping(_mapping(session.get("artifacts")).get("final_evidence"))
        identity = {"registry_id": value["registry_id"], "mission_id": mission.get("mission_id"), "goal_id": goal_id, "session_id": session.get("session_id")}
        record_id = f"goal-execution-completion-{fingerprint(identity)[:20]}"
        record = {
            "record_id": record_id,
            "mission_id": mission.get("mission_id"),
            "goal_id": goal_id,
            "session_id": session.get("session_id"),
            "execution_status": "completed",
            "transaction_status": tx.get("transaction_status"),
            "transaction_fingerprint": _mapping(session.get("artifact_fingerprints")).get("transaction_result"),
            "evidence_fingerprint": evidence.get("final_evidence_fingerprint"),
            "completed_at": goal.get("completed_at") or time_text(now),
        }
        record["record_fingerprint"] = fingerprint(record)
        existing = _mapping(records.get(record_id))
        if existing and existing != record:
            raise ValueError("goal_completion_record_mismatch")
        records[record_id] = record
        for entry_id, entry in list(entries.items()):
            item = _mapping(entry)
            if item.get("session_id") == session.get("session_id") and item.get("entry_status") == "registered":
                item["entry_status"] = "consumed"
                item["consumed_at"] = time_text(now)
                item["execution_result_fingerprint"] = record["record_fingerprint"]
                entries[entry_id] = seal_registry_entry(item)

    value["entries"] = entries
    value["completion_records"] = records
    value["completion_record_order"] = sorted(records)
    value["completion_count"] = len(records)
    value["registry_status"] = "closed"
    value["closed_at"] = value.get("closed_at") or time_text(now)
    value["updated_at"] = time_text(now)
    return seal_goal_execution_registry(value)


def save_goal_execution_registry(
    registry: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)

    if destination.exists() and _unsafe(destination):
        raise ValueError("unsafe_registry_path")

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if _unsafe(destination.parent):
        raise ValueError("unsafe_registry_directory")

    value = seal_goal_execution_registry(registry)
    reasons = validate_goal_execution_registry(value)
    if reasons:
        raise ValueError(";".join(reasons))

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, destination)
    return value


def load_goal_execution_registry(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)

    if _unsafe(source):
        raise ValueError("unsafe_registry_path")

    try:
        value = json.loads(
            source.read_text(encoding="utf-8-sig")
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("invalid_registry_json") from exc

    reasons = validate_goal_execution_registry(value)
    if reasons:
        raise ValueError(";".join(reasons))

    return value


__all__ = [
    "CONTRACT",
    "ENTRY_CONTRACT",
    "SUPPORTED_GOAL_TYPES",
    "create_goal_execution_registry",
    "finalize_goal_execution_registry",
    "load_goal_execution_registry",
    "mark_registry_entry_consumed",
    "pending_goal_execution_requests",
    "register_goal_execution_request",
    "save_goal_execution_registry",
    "seal_goal_execution_registry",
    "seal_registry_entry",
    "validate_goal_execution_registry",
    "validate_registry_entry",
]
