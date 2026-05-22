from __future__ import annotations

from pathlib import Path


def _executor(tmp_path: Path, calls: list[str] | None = None):
    from core.runtime.step_executor import StepExecutor

    executor = StepExecutor(workspace_root=str(tmp_path / "workspace"))

    def handler(step, task, context, previous_result):
        if calls is not None:
            calls.append("called")
        return {
            "ok": True,
            "message": "activation ok",
            "final_answer": "activation ok",
            "step_type": "activation_noop",
        }

    executor.register_handler("activation_noop", handler)
    return executor


def _metadata(result: dict) -> dict:
    return result["runtime_execution_result"]["metadata"]


def test_audit_only_activation_is_existing_behavior(tmp_path: Path) -> None:
    result = _executor(tmp_path).execute_step({"type": "activation_noop"})
    metadata = _metadata(result)

    assert result["ok"] is True
    assert result["blocked"] is False
    assert metadata["constitutional_probe"] is True
    assert "constitutional_activation_mode" not in metadata


def test_advisory_mode_attaches_warnings_only(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "advisory",
            "constitutional_probe_from_status": "verified",
            "constitutional_probe_to_status": "running",
        }
    )
    metadata = _metadata(result)

    assert calls == ["called"]
    assert result["ok"] is True
    assert result["blocked"] is False
    assert metadata["constitutional_activation_mode"] == "advisory"
    assert metadata["constitutional_blocked"] is False
    assert metadata["constitutional_advisory"] is True
    assert metadata["constitutional_enforcement_snapshot"]["would_block"] is True


def test_selective_activation_blocks_safe_hard_block_candidate(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "verified",
            "constitutional_probe_to_status": "running",
            "constitutional_block_recommended": True,
        }
    )
    metadata = _metadata(result)

    assert calls == []
    assert result["ok"] is False
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["error_type"] == "constitutionally_blocked"
    assert metadata["constitutional_activation_mode"] == "selective_activation"
    assert metadata["constitutional_blocked"] is True
    assert metadata["constitutional_enforcement_snapshot"]["classification"] == "block_recommended"


def test_selective_activation_blocks_sealed_resurrection(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "sealed",
            "constitutional_probe_to_status": "running",
        }
    )
    metadata = _metadata(result)

    assert calls == []
    assert result["blocked"] is True
    assert metadata["constitutional_activation_reason"] == "sealed_resurrection_attempt"


def test_selective_activation_blocks_replayed_queue_reset(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "replayed",
            "constitutional_probe_to_status": "queued",
        }
    )
    metadata = _metadata(result)

    assert calls == []
    assert result["blocked"] is True
    assert metadata["constitutional_activation_reason"] == "replayed_queued_reset_loop"


def test_selective_activation_does_not_block_canonical_transition(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "running",
            "constitutional_probe_to_status": "executed",
        }
    )

    assert calls == ["called"]
    assert result["ok"] is True
    assert result["blocked"] is False
    assert _metadata(result)["constitutional_blocked"] is False


def test_selective_activation_does_not_block_review_required(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "queued",
            "constitutional_probe_to_status": "executed",
        }
    )
    snapshot = _metadata(result)["constitutional_enforcement_snapshot"]

    assert calls == ["called"]
    assert result["ok"] is True
    assert result["blocked"] is False
    assert snapshot["classification"] == "review_required"


def test_selective_activation_does_not_block_observe_only(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _executor(tmp_path, calls).execute_step(
        {
            "type": "activation_noop",
            "constitutional_activation_mode": "selective_activation",
            "constitutional_probe_from_status": "running",
            "constitutional_probe_to_status": "committed",
        }
    )
    snapshot = _metadata(result)["constitutional_enforcement_snapshot"]

    assert calls == ["called"]
    assert result["ok"] is True
    assert result["blocked"] is False
    assert snapshot["classification"] == "observe_only"


def test_runtime_execution_result_abi_remains_stable_for_activation_metadata() -> None:
    from core.runtime.runtime_execution_result import RuntimeExecutionResult

    payload = RuntimeExecutionResult.from_runtime_mapping(
        {
            "ok": False,
            "blocked": True,
            "error_type": "constitutionally_blocked",
            "metadata": {
                "constitutional_activation": True,
                "constitutional_activation_mode": "selective_activation",
                "constitutional_blocked": True,
            },
        }
    ).to_dict()

    assert payload["blocked"] is True
    assert payload["failed"] is False
    assert payload["metadata"]["constitutional_activation"] is True
    assert payload["metadata"]["constitutional_blocked"] is True


def test_scheduler_agent_loop_and_repair_bridge_remain_unwired() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        root / "core/tasks/scheduler.py",
        root / "core/agent/agent_loop.py",
        root / "core/runtime/repair_transaction_execution_bridge.py",
    ]
    markers = (
        "constitutional_activation_mode",
        "constitutionally_blocked",
        "_zero_v7331_execute_step_selective_activation",
    )

    for path in forbidden:
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
