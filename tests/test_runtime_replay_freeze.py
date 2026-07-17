from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_replay_freeze import (

    ReplayMode,
    create_replay_run,
    replay_read_only,
)
from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_transaction_registry import create_transaction, list_transactions
import pytest

pytestmark = [pytest.mark.integration]



def test_replay_read_is_read_only_and_does_not_require_authority() -> None:
    surface = classify_runtime_surface("replay_read")

    assert surface.read_only is True
    assert surface.requires_authority is False
    assert surface.requires_transaction is False


def test_replay_read_does_not_create_transaction() -> None:
    before = len(list_transactions())
    result = replay_read_only(_event_log(surface="replay_read"))

    assert result["mode"] == "read_only"
    assert result["transaction_required"] is False
    assert len(list_transactions()) == before


def test_replay_read_does_not_execute_subprocess() -> None:
    result = replay_read_only(
        [
            {
                "sequence": 2,
                "surface": "replay_read",
                "event_type": "subprocess",
                "command": "SHOULD_NOT_RUN",
            }
        ]
    )

    assert result["result_state"] == "verified"
    assert result["mutation_attempted"] is False
    assert result["authority_required"] is False


def test_replay_context_alone_is_not_execution_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "replay_mutation", "target_path": "workspace/shared/replay.txt"},
        context={"replay_context": {"replay_run_id": "replay-run-only"}},
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert result["runtime_transaction"]["state"] == "blocked"


def test_replay_mutation_requires_authority() -> None:
    surface = classify_runtime_surface("replay_mutation")

    assert surface.requires_authority is True
    assert surface.requires_transaction is True
    assert surface.mutation is True


def test_replay_mutation_requires_transaction(tmp_path: Path) -> None:
    from tests.authority_test_support import owned_step_executor

    result = owned_step_executor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "replay_mutation",
            "target_path": "workspace/shared/replay-mutation.txt",
            "replay_source": "replay:source",
        },
        context={"execution_authority": _authority("replay_mutation")},
    )

    assert result["runtime_transaction"]["surface"] == "replay_mutation"
    assert result["runtime_transaction"]["replay_source"] == "replay:source"


def test_replay_mutation_creates_new_transaction_with_replay_source(tmp_path: Path) -> None:
    from tests.authority_test_support import owned_step_executor

    original = create_transaction(
        task_id="task-original",
        step_id="step-original",
        trace_id="trace-original",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/original.txt"],
    )
    result = owned_step_executor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "replay_mutation",
            "target_path": "workspace/shared/replay-new.txt",
            "replay_source": "replay:original",
            "original_transaction_id": original.transaction_id,
            "original_trace_id": original.trace_id,
        },
        context={"execution_authority": _authority("replay_mutation")},
    )

    runtime_tx = result["runtime_transaction"]
    assert runtime_tx["transaction_id"] != original.transaction_id
    assert runtime_tx["replay_source"] == "replay:original"
    assert runtime_tx["original_transaction_id"] == original.transaction_id
    assert runtime_tx["original_trace_id"] == "trace-original"


def test_replay_mutation_does_not_overwrite_original_transaction(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor
    from core.runtime.runtime_transaction_registry import get_transaction

    original = create_transaction(
        task_id="task-source",
        step_id="step-source",
        trace_id="trace-source",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/source.txt"],
    )
    before = original.to_dict()

    StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "replay_mutation",
            "target_path": "workspace/shared/source.txt",
            "replay_source": "replay:source",
            "original_transaction_id": original.transaction_id,
            "original_trace_id": original.trace_id,
        },
        context={"execution_authority": _authority("replay_mutation")},
    )

    assert get_transaction(original.transaction_id).to_dict() == before


def test_replay_result_has_replay_run_id() -> None:
    result = replay_read_only(_event_log(surface="replay_read"))

    assert result["replay_run_id"].startswith("replay_run:")


def test_replay_result_is_stable_across_repeated_runs() -> None:
    first = replay_read_only(_event_log(surface="replay_read", timestamp="2026-01-01T00:00:00Z"))
    second = replay_read_only(_event_log(surface="replay_read", timestamp="2026-05-26T00:00:00Z"))

    assert first["normalized_digest"] == second["normalized_digest"]
    assert first["replay_run_id"] == second["replay_run_id"]


def _event_log(*, surface: str, timestamp: str = "2026-05-26T01:02:03Z") -> list[dict]:
    return [
        {
            "event_id": "event-1",
            "sequence": 1,
            "surface": surface,
            "event_type": surface,
            "trace_id": "trace-replay",
            "timestamp": timestamp,
            "audit_refs": ["audit:source"],
        }
    ]


def _authority(action_type: str) -> dict:
    return {
        "task_id": f"task-{action_type}",
        "step_id": f"step-{action_type}",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{action_type}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{action_type}",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
