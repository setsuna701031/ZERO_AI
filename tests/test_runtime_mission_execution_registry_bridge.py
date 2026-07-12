from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from core.runtime.runtime_goal_execution_registry import (
    load_goal_execution_registry,
)
from core.runtime.runtime_mission_execution_registry_bridge import (
    CONTRACT,
    sync_mission_execution_registry,
)
from core.runtime.runtime_operator_session import (
    fingerprint,
    save_runtime_session,
    seal_session,
)

NOW = "2026-07-12T00:00:00+00:00"


def _session(
    *,
    session_id: str = "session-1",
    status: str = "waiting_for_candidate_bundle",
) -> dict:
    natural_task = {
        "task_id": "mission-1:goal-1:attempt-1",
        "text": "Append a controlled comment.",
        "mission_id": "mission-1",
        "goal_id": "goal-1",
        "goal_title": "Update app.py",
        "target_files": ["app.py"],
        "approved_target_scope": ["app.py"],
        "acceptance_criteria": ["app.py updated"],
        "validation_requirements": ["python_compile"],
    }
    session = {
        "contract": "zero.runtime.operator_session.v1",
        "session_id": session_id,
        "session_status": status,
        "task_id": natural_task["task_id"],
        "natural_task": natural_task,
        "created_at": NOW,
        "updated_at": NOW,
        "expires_at": "2026-07-19T00:00:00+00:00",
        "target_root_identity": "target-root-identity",
        "workspace_root_identity": "workspace-root-identity",
        "operator_context": {},
        "current_phase": "active_execution_prepared",
        "required_action": (
            "candidate_bundle"
            if status == "waiting_for_candidate_bundle"
            else "operator_approval"
        ),
        "required_input_contract": (
            "zero.runtime.transaction_candidate_bundle.v1"
            if status == "waiting_for_candidate_bundle"
            else "zero.runtime.operator_approval_gate.v1"
        ),
        "checkpoints": [],
        "artifacts": {},
        "artifact_fingerprints": {},
        "identity_chain": {},
        "phase_history": [],
        "pause_reason": None,
        "failure": None,
        "completed": False,
        "processed_input_ids": [],
        "operator_actions": [],
        "audit_record": {
            "event_type": "runtime_session_created",
            "created_at": NOW,
        },
    }
    return seal_session(session)


def _goal(
    *,
    goal_id: str = "goal-1",
) -> dict:
    value = {
        "goal_id": goal_id,
        "mission_id": "mission-1",
        "goal_type": "modify",
        "goal_title": "Update app.py",
        "goal_description": "Append a controlled comment.",
        "target_scope": ["app.py"],
        "excluded_scope": [],
        "acceptance_criteria": ["app.py updated"],
        "validation_requirements": ["python_compile"],
        "operator_context": {
            "authoring_instruction": {
                "authoring_strategy": "append_text",
                "append_text": "\n# bridge\n",
                "target_files": ["app.py"],
            }
        },
    }
    value["goal_fingerprint"] = fingerprint(
        {
            key: deepcopy(item)
            for key, item in value.items()
            if key != "goal_fingerprint"
        }
    )
    return value


def _mission(
    *,
    mission_path: Path,
    session_path: Path,
    session_id: str = "session-1",
) -> dict:
    return {
        "mission_id": "mission-1",
        "mission_path": str(mission_path),
        "goal_order": ["goal-1"],
        "goals": {
            "goal-1": _goal(),
        },
        "session_references": {
            "goal-1": [
                {
                    "session_id": session_id,
                    "session_path": str(session_path),
                    "session_fingerprint": "ignored-by-bridge",
                    "mission_id": "mission-1",
                    "goal_id": "goal-1",
                    "attempt": 1,
                    "archived": False,
                }
            ]
        },
    }


def test_bridge_registers_candidate_ready_session(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    session = _session()
    save_runtime_session(session, session_path)

    result = sync_mission_execution_registry(
        _mission(
            mission_path=mission_path,
            session_path=session_path,
        ),
        target_root=target,
        workspace_root=workspace,
        runtime_config={
            "goal_execution_artifact_root": (
                tmp_path / "artifacts"
            ),
        },
        now=NOW,
    )

    assert result["contract"] == CONTRACT
    assert result["mission_id"] == "mission-1"
    assert result["registered_session_ids"] == ["session-1"]
    assert result["blocked_sessions"] == []
    assert result["pending_request_session_ids"] == ["session-1"]
    assert result["pending_request_count"] == 1
    assert result["workspace_mutated"] is False
    assert result["worker_invoked"] is False
    assert result["executor_invoked"] is False
    assert result["transaction_invoked"] is False

    overlay = result["runtime_config_overlay"]
    assert "goal_execution_requests" in overlay
    assert "session-1" in overlay["goal_execution_requests"]
    assert (
        overlay["goal_execution_requests"]["session-1"]["goal"][
            "goal_id"
        ]
        == "goal-1"
    )
    assert (
        overlay["goal_execution_requests"]["session-1"][
            "artifact_root"
        ].replace("\\", "/").endswith(
            "artifacts/session-1"
        )
    )


def test_bridge_persists_registry(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(_session(), session_path)

    result = sync_mission_execution_registry(
        _mission(
            mission_path=mission_path,
            session_path=session_path,
        ),
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    registry_path = Path(result["registry_path"])
    assert registry_path.exists()

    registry = load_goal_execution_registry(registry_path)
    assert registry["registry_id"] == (
        "goal-execution-registry-mission-1"
    )
    assert registry["entry_count"] == 1
    assert registry["registry_fingerprint"] == (
        result["registry_fingerprint"]
    )


def test_bridge_is_idempotent(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(_session(), session_path)

    mission = _mission(
        mission_path=mission_path,
        session_path=session_path,
    )

    first = sync_mission_execution_registry(
        mission,
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )
    second = sync_mission_execution_registry(
        mission,
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    assert first["registry_fingerprint"] == (
        second["registry_fingerprint"]
    )
    assert first["pending_request_count"] == 1
    assert second["pending_request_count"] == 1


def test_non_candidate_session_is_skipped(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(
        _session(
            status="waiting_for_operator_approval"
        ),
        session_path,
    )

    result = sync_mission_execution_registry(
        _mission(
            mission_path=mission_path,
            session_path=session_path,
        ),
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    assert result["registered_session_ids"] == []
    assert result["skipped_session_ids"] == ["session-1"]
    assert result["pending_request_count"] == 0


def test_archived_reference_is_ignored(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(_session(), session_path)

    mission = _mission(
        mission_path=mission_path,
        session_path=session_path,
    )
    mission["session_references"]["goal-1"][0][
        "archived"
    ] = True

    result = sync_mission_execution_registry(
        mission,
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    assert result["registered_session_ids"] == []
    assert result["skipped_session_ids"] == []
    assert result["pending_request_count"] == 0


def test_invalid_session_reference_is_blocked(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    mission = _mission(
        mission_path=mission_path,
        session_path=tmp_path / "missing.json",
    )

    result = sync_mission_execution_registry(
        mission,
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    assert result["registered_session_ids"] == []
    assert result["pending_request_count"] == 0
    assert len(result["blocked_sessions"]) == 1
    assert result["blocked_sessions"][0]["goal_id"] == "goal-1"


def test_session_identity_mismatch_is_blocked(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(
        _session(session_id="different-session"),
        session_path,
    )

    result = sync_mission_execution_registry(
        _mission(
            mission_path=mission_path,
            session_path=session_path,
            session_id="session-1",
        ),
        target_root=target,
        workspace_root=workspace,
        runtime_config={},
        now=NOW,
    )

    assert result["registered_session_ids"] == []
    assert result["pending_request_count"] == 0
    assert result["blocked_sessions"] == [
        {
            "goal_id": "goal-1",
            "session_id": "session-1",
            "reason": "session_identity_mismatch",
        }
    ]


def test_bridge_preserves_existing_runtime_config(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    workspace = tmp_path / "workspace"
    target.mkdir()
    workspace.mkdir()

    mission_path = tmp_path / "mission.json"
    session_path = tmp_path / "session.json"
    save_runtime_session(_session(), session_path)

    result = sync_mission_execution_registry(
        _mission(
            mission_path=mission_path,
            session_path=session_path,
        ),
        target_root=target,
        workspace_root=workspace,
        runtime_config={
            "existing_flag": True,
            "lease_seconds": 30,
        },
        now=NOW,
    )

    overlay = result["runtime_config_overlay"]
    assert overlay["existing_flag"] is True
    assert overlay["lease_seconds"] == 30
    assert "goal_execution_requests" in overlay
    assert "goal_execution_registry_path" in overlay
    assert (
        "goal_execution_registry_fingerprint"
        in overlay
    )
