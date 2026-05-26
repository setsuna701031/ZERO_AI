from __future__ import annotations

from pathlib import Path
import sys


def test_runtime_execution_request_missing_authority_metadata_is_blocked(tmp_path: Path) -> None:
    from core.runtime.execution_gateway import execute_runtime_request
    from core.runtime.runtime_execution_request import RuntimeExecutionRequest

    result = execute_runtime_request(
        RuntimeExecutionRequest(
            execution_type="subprocess",
            command=(sys.executable, "-c", "print('SHOULD_NOT_RUN')"),
            metadata={},
        ),
        workspace_root=str(tmp_path),
    )

    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["metadata"]["blocked"] is True
    assert payload["metadata"]["blocked_reason"] == "missing_authority_metadata"
    assert payload["metadata"]["audit_event"]["reason"] == "missing_authority_metadata"
    assert payload["metadata"]["replay_event"]["decision"] == "blocked"


def test_safe_subprocess_gateway_supplies_authority_metadata(tmp_path: Path) -> None:
    from core.runtime.execution_gateway import safe_subprocess_run

    result = safe_subprocess_run(
        (sys.executable, "-c", "print('AUTH_OK')"),
        cwd=str(tmp_path),
        timeout=10,
    )

    assert result["ok"] is True
    assert "AUTH_OK" in result["stdout"]
    metadata = result["metadata"]
    for field in (
        "task_id",
        "step_id",
        "authority_source",
        "runtime_session",
        "approval_state",
        "policy_result",
        "trace_id",
    ):
        assert metadata.get(field)
    assert metadata["authority_validation"]["ok"] is True


def test_step_executor_missing_authority_leaves_audit_evidence_replay_reason(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "apply_patch",
            "target_path": "workspace/shared/blocked.txt",
            "old_text": "before",
            "new_text": "after",
        }
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["authority_decision"]["reason"] == "missing_authority_metadata"
    assert result["audit_event"]["reason"] == "missing_authority_metadata"
    assert result["evidence"]["reason"] == "missing_authority_metadata"
    assert result["replay_event"]["decision"] == "blocked"
    assert not (tmp_path / "shared" / "blocked.txt").exists()


def test_execution_gateway_is_only_runtime_subprocess_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (root / "core" / "runtime").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "subprocess.run(" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        if rel != "core/runtime/executor.py":
            offenders.append(rel)

    assert offenders == []
