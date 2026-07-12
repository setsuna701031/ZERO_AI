from __future__ import annotations

from copy import deepcopy

import pytest

import core.runtime.runtime_goal_execution_dispatch as dispatch_module
from core.runtime.runtime_goal_execution_dispatch import (
    CONTRACT,
    build_goal_execution_dispatch,
    seal_goal_execution_dispatch,
    validate_goal_execution_dispatch,
)
from core.runtime.runtime_operator_session import fingerprint

NOW = "2026-07-12T00:00:00+00:00"


def _session(
    *,
    goal_type: str = "modify",
    scope: list[str] | None = None,
    excluded_scope: list[str] | None = None,
    authoring_instruction: dict | None = None,
    session_status: str = "waiting_for_candidate_bundle",
) -> dict:
    natural_task = {
        "task_id": "mission-1:goal-1:attempt-1",
        "text": "Update app.py safely.",
        "mission_id": "mission-1",
        "goal_id": "goal-1",
        "goal_title": "Update app.py",
        "goal_type": goal_type,
        "approved_target_scope": scope if scope is not None else ["app.py"],
        "target_files": scope if scope is not None else ["app.py"],
        "excluded_scope": excluded_scope or [],
        "acceptance_criteria": ["app.py updated"],
        "validation_requirements": ["python_compile"],
        "authoring_instruction": (
            authoring_instruction
            if authoring_instruction is not None
            else {
                "strategy": "append_text",
                "target_path": "app.py",
                "append_text": "\n# dispatched\n",
            }
        ),
    }
    natural_task["goal_fingerprint"] = fingerprint(
        {
            key: deepcopy(value)
            for key, value in natural_task.items()
            if key != "goal_fingerprint"
        }
    )
    return {
        "contract": "zero.runtime.operator_session.v1",
        "session_id": "session-1",
        "session_status": session_status,
        "session_fingerprint": "session-fingerprint-1",
        "required_action": "candidate_bundle",
        "required_input_contract": "zero.runtime.candidate_bundle.v1",
        "natural_task": natural_task,
    }


def _fake_create_goal_execution_request(
    goal,
    session,
    *,
    operator_context,
    now,
):
    unsigned = {
        "contract": dispatch_module.GOAL_EXECUTION_REQUEST_CONTRACT,
        "request_id": "execution-request-1",
        "session_id": session["session_id"],
        "mission_id": goal["mission_id"],
        "goal_id": goal["goal_id"],
        "goal_type": goal["goal_type"],
        "goal": deepcopy(goal),
        "operator_context": deepcopy(operator_context),
        "created_at": now,
    }
    unsigned["execution_request_fingerprint"] = fingerprint(unsigned)
    return unsigned


@pytest.fixture(autouse=True)
def _stub_goal_executor(monkeypatch):
    monkeypatch.setattr(
        dispatch_module,
        "create_goal_execution_request",
        _fake_create_goal_execution_request,
    )


def test_build_dispatch_from_waiting_session() -> None:
    result = build_goal_execution_dispatch(
        _session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )

    assert result["contract"] == CONTRACT
    assert result["dispatch_status"] == "ready"
    assert result["session_id"] == "session-1"
    assert result["mission_id"] == "mission-1"
    assert result["goal_id"] == "goal-1"
    assert result["goal_type"] == "modify"
    assert result["approved_scope"] == ["app.py"]
    assert result["workspace_mutated"] is False
    assert result["transaction_invoked"] is False
    assert result["operator_input_submitted"] is False
    assert validate_goal_execution_dispatch(result) == []


def test_dispatch_is_deterministic_for_same_inputs() -> None:
    first = build_goal_execution_dispatch(
        _session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    second = build_goal_execution_dispatch(
        _session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )

    assert first == second
    assert first["dispatch_id"] == second["dispatch_id"]
    assert first["dispatch_fingerprint"] == second["dispatch_fingerprint"]


def test_non_candidate_session_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="session_not_waiting_for_candidate_bundle",
    ):
        build_goal_execution_dispatch(
            _session(session_status="waiting_for_operator_approval"),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_missing_scope_is_rejected() -> None:
    with pytest.raises(ValueError, match="approved_scope_required"):
        build_goal_execution_dispatch(
            _session(scope=[]),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_scope_intersection_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="approved_scope_intersects_excluded_scope",
    ):
        build_goal_execution_dispatch(
            _session(
                scope=["app.py"],
                excluded_scope=["app.py"],
            ),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_modify_without_authoring_instruction_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="authoring_instruction_required",
    ):
        build_goal_execution_dispatch(
            _session(authoring_instruction={}),
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_executable_context_is_rejected() -> None:
    session = _session()
    session["natural_task"]["operator_context"] = {
        "shell": "python app.py",
    }

    with pytest.raises(
        ValueError,
        match="executable_operator_context_forbidden",
    ):
        build_goal_execution_dispatch(
            session,
            artifact_root="C:/artifacts/session-1",
            now=NOW,
        )


def test_tampered_dispatch_fingerprint_is_detected() -> None:
    result = build_goal_execution_dispatch(
        _session(),
        artifact_root="C:/artifacts/session-1",
        now=NOW,
    )
    result["goal_id"] = "tampered-goal"

    reasons = validate_goal_execution_dispatch(result)

    assert "goal_execution_dispatch_fingerprint_mismatch" in reasons
    assert "dispatch_request_goal_mismatch" in reasons


def test_seal_replaces_existing_fingerprint() -> None:
    value = {
        "contract": CONTRACT,
        "dispatch_id": "dispatch-1",
        "dispatch_fingerprint": "stale",
    }

    sealed = seal_goal_execution_dispatch(value)

    assert sealed["dispatch_fingerprint"] != "stale"
    assert sealed["dispatch_fingerprint"] == fingerprint(
        {
            "contract": CONTRACT,
            "dispatch_id": "dispatch-1",
        }
    )
