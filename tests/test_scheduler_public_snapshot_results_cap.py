from __future__ import annotations

from core.tasks.scheduler import Scheduler
import pytest

pytestmark = [pytest.mark.llm]




def test_normalize_task_schema_caps_results_without_deep_runtime_payload(tmp_path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))

    huge_nested = {
        "runtime_execution_result": {
            "metadata": {
                "canonical_evidence": {
                    "evidence_snapshot": {
                        "payload": ["x" * 1000 for _ in range(50)]
                    }
                }
            }
        }
    }

    task = {
        "task_id": "task_public_snapshot_cap",
        "task_name": "task_public_snapshot_cap",
        "status": "queued",
        "steps": [{"type": "read_file"}],
        "results": [
            {
                "step_index": i,
                "step": {"type": "llm" if i == 4 else "read_file"},
                "result": {
                    "ok": True,
                    "step_type": "llm" if i == 4 else "read_file",
                    "message": "ok",
                    "metadata": huge_nested,
                },
            }
            for i in range(5)
        ],
    }

    normalized = scheduler._normalize_task_schema(task)
    results = normalized.get("results")

    assert isinstance(results, list)
    assert len(results) == 3
    assert results[-1]["step_index"] == 4
    assert results[-1]["step_type"] == "llm"
    assert "metadata" not in results[-1]
    assert "runtime_execution_result" not in results[-1]


def test_normalize_task_schema_result_summary_keeps_blocked_error_signal(tmp_path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))

    task = {
        "task_id": "task_public_snapshot_blocked",
        "task_name": "task_public_snapshot_blocked",
        "status": "blocked",
        "results": [
            {
                "step_index": 2,
                "step": {"type": "write_file"},
                "result": {
                    "ok": False,
                    "blocked": True,
                    "failed": False,
                    "error_type": "execution_authority_denied",
                    "message": "approval_state_not_allowed",
                },
            }
        ],
    }

    normalized = scheduler._normalize_task_schema(task)
    result = normalized["results"][0]

    assert result["step_index"] == 2
    assert result["step_type"] == "write_file"
    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["error_type"] == "execution_authority_denied"
    assert result["message"] == "approval_state_not_allowed"
