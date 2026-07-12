from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from core.runtime.runtime_goal_execution_registry import (
    CONTRACT,
    ENTRY_CONTRACT,
    create_goal_execution_registry,
    load_goal_execution_registry,
    mark_registry_entry_consumed,
    pending_goal_execution_requests,
    register_goal_execution_request,
    save_goal_execution_registry,
    validate_goal_execution_registry,
    validate_registry_entry,
)
from core.runtime.runtime_operator_session import fingerprint

NOW = "2026-07-12T00:00:00+00:00"


def _mission() -> dict:
    return {
        "mission_id": "mission-1",
        "planner_output_summary": {
            "excluded_scope": ["secrets.txt"],
        },
    }


def _goal(
    *,
    goal_type: str = "modify",
    scope: list[str] | None = None,
    excluded_scope: list[str] | None = None,
    operator_context: dict | None = None,
) -> dict:
    value = {
        "goal_id": "goal-1",
        "mission_id": "mission-1",
        "goal_type": goal_type,
        "goal_title": "Update app.py",
        "goal_description": "Append a controlled comment.",
        "target_scope": ["app.py"] if scope is None else scope,
        "excluded_scope": (
            ["secrets.txt"]
            if excluded_scope is None
            else excluded_scope
        ),
        "acceptance_criteria": ["app.py updated"],
        "validation_requirements": ["python_compile"],
        "operator_context": (
            {
                "authoring_instruction": {
                    "authoring_strategy": "append_text",
                    "append_text": "\n# registry\n",
                    "target_files": ["app.py"],
                }
            }
            if operator_context is None
            else operator_context
        ),
    }
    value["goal_fingerprint"] = fingerprint(
        {
            key: deepcopy(item)
            for key, item in value.items()
            if key != "goal_fingerprint"
        }
    )
    return value


def _session(
    *,
    status: str = "waiting_for_candidate_bundle",
) -> dict:
    return {
        "session_id": "session-1",
        "session_status": status,
        "required_action": "candidate_bundle",
        "required_input_contract": (
            "zero.runtime.transaction_candidate_bundle.v1"
        ),
        "session_fingerprint": "session-fingerprint-1",
    }


def test_create_empty_registry() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    assert registry["contract"] == CONTRACT
    assert registry["registry_id"] == "registry-1"
    assert registry["registry_status"] == "active"
    assert registry["entries"] == {}
    assert registry["entry_order"] == []
    assert registry["entry_count"] == 0
    assert validate_goal_execution_registry(registry) == []


def test_register_and_project_pending_request() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )

    assert registry["entry_count"] == 1
    entry_id = registry["entry_order"][0]
    entry = registry["entries"][entry_id]

    assert entry["contract"] == ENTRY_CONTRACT
    assert entry["entry_status"] == "registered"
    assert entry["mission_id"] == "mission-1"
    assert entry["goal_id"] == "goal-1"
    assert entry["session_id"] == "session-1"
    assert entry["approved_scope"] == ["app.py"]
    assert entry["workspace_mutated"] is False
    assert entry["transaction_invoked"] is False
    assert validate_registry_entry(entry) == []

    pending = pending_goal_execution_requests(registry)

    assert list(pending) == ["session-1"]
    specification = pending["session-1"]
    assert specification["goal"]["goal_id"] == "goal-1"
    assert specification["goal"]["mission_id"] == "mission-1"
    assert specification["goal"]["goal_type"] == "modify"
    assert specification["goal"]["target_scope"] == ["app.py"]
    assert specification["artifact_root"] == (
        "C:/artifacts/session-1"
    )
    assert specification["registry_entry_id"] == entry_id
    assert (
        specification["execution_request_fingerprint"]
        == entry["execution_request_fingerprint"]
    )


def test_registration_is_idempotent() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    first = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    second = register_goal_execution_request(
        first,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )

    assert second["entry_count"] == 1
    assert second["entry_order"] == first["entry_order"]
    assert second["registry_fingerprint"] == (
        first["registry_fingerprint"]
    )


def test_non_candidate_session_is_rejected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    with pytest.raises(
        ValueError,
        match="session_not_waiting_for_candidate_bundle",
    ):
        register_goal_execution_request(
            registry,
            mission=_mission(),
            goal=_goal(),
            session=_session(
                status="waiting_for_operator_approval"
            ),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_missing_scope_is_rejected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    with pytest.raises(
        ValueError,
        match="approved_scope_required",
    ):
        register_goal_execution_request(
            registry,
            mission=_mission(),
            goal=_goal(scope=[]),
            session=_session(),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_scope_intersection_is_rejected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    with pytest.raises(
        ValueError,
        match="approved_scope_intersects_excluded_scope",
    ):
        register_goal_execution_request(
            registry,
            mission=_mission(),
            goal=_goal(
                scope=["app.py"],
                excluded_scope=["app.py"],
            ),
            session=_session(),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_executable_operator_context_is_rejected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )

    with pytest.raises(
        ValueError,
        match="executable_operator_context_forbidden",
    ):
        register_goal_execution_request(
            registry,
            mission=_mission(),
            goal=_goal(
                operator_context={
                    "shell": "python app.py",
                }
            ),
            session=_session(),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_mark_entry_consumed_removes_it_from_pending() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    entry_id = registry["entry_order"][0]

    consumed = mark_registry_entry_consumed(
        registry,
        entry_id=entry_id,
        execution_result_fingerprint="result-fingerprint-1",
        now=NOW,
    )

    entry = consumed["entries"][entry_id]
    assert entry["entry_status"] == "consumed"
    assert entry["execution_result_fingerprint"] == (
        "result-fingerprint-1"
    )
    assert pending_goal_execution_requests(consumed) == {}
    assert validate_goal_execution_registry(consumed) == []


def test_consumption_is_idempotent_for_same_result() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    entry_id = registry["entry_order"][0]

    first = mark_registry_entry_consumed(
        registry,
        entry_id=entry_id,
        execution_result_fingerprint="result-fingerprint-1",
        now=NOW,
    )
    second = mark_registry_entry_consumed(
        first,
        entry_id=entry_id,
        execution_result_fingerprint="result-fingerprint-1",
        now=NOW,
    )

    assert first["registry_fingerprint"] == (
        second["registry_fingerprint"]
    )


def test_consumption_mismatch_is_rejected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    entry_id = registry["entry_order"][0]

    consumed = mark_registry_entry_consumed(
        registry,
        entry_id=entry_id,
        execution_result_fingerprint="result-fingerprint-1",
        now=NOW,
    )

    with pytest.raises(
        ValueError,
        match="registry_entry_consumption_mismatch",
    ):
        mark_registry_entry_consumed(
            consumed,
            entry_id=entry_id,
            execution_result_fingerprint="different-result",
            now=NOW,
        )


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root=str(tmp_path / "artifacts"),
        now=NOW,
    )

    saved = save_goal_execution_registry(
        registry,
        path,
    )
    loaded = load_goal_execution_registry(path)

    assert loaded == saved
    assert loaded["registry_fingerprint"] == (
        saved["registry_fingerprint"]
    )
    assert validate_goal_execution_registry(loaded) == []


def test_utf8_bom_load_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    saved = save_goal_execution_registry(
        registry,
        path,
    )

    raw = path.read_text(encoding="utf-8")
    path.write_text(
        "\ufeff" + raw,
        encoding="utf-8",
        newline="\n",
    )

    loaded = load_goal_execution_registry(path)

    assert loaded == saved


def test_tampered_registry_fingerprint_is_detected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry["registry_status"] = "closed"

    reasons = validate_goal_execution_registry(registry)

    assert (
        "goal_execution_registry_fingerprint_mismatch"
        in reasons
    )


def test_tampered_entry_fingerprint_is_detected() -> None:
    registry = create_goal_execution_registry(
        registry_id="registry-1",
        now=NOW,
    )
    registry = register_goal_execution_request(
        registry,
        mission=_mission(),
        goal=_goal(),
        session=_session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    entry_id = registry["entry_order"][0]
    registry["entries"][entry_id]["goal_id"] = "tampered"

    reasons = validate_goal_execution_registry(registry)

    assert "registry_entry_fingerprint_mismatch" in reasons
    assert "registry_request_goal_mismatch" in reasons
