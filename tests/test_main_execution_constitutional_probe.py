from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def _executor(tmp_path: Path):
    from core.runtime.step_executor import StepExecutor

    executor = StepExecutor(workspace_root=str(tmp_path / "workspace"))
    executor.register_handler(
        "noop_probe",
        lambda step, task, context, previous_result: {
            "ok": True,
            "message": "probe ok",
            "final_answer": "probe ok",
            "step_type": "noop_probe",
        },
    )
    return executor


def test_step_executor_default_public_shape_is_unchanged(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    step = {"type": "noop_probe"}

    without_probe = executor.execute_step(step, constitutional_probe=False)
    with_probe = executor.execute_step(step)

    assert set(with_probe.keys()) == set(without_probe.keys())
    assert with_probe["ok"] is True
    assert with_probe["executed"] is True
    assert with_probe["blocked"] is False
    assert with_probe["failed"] is False


def test_step_executor_result_includes_constitutional_probe_metadata(tmp_path: Path) -> None:
    result = _executor(tmp_path).execute_step({"type": "noop_probe"})
    metadata = result["runtime_execution_result"]["metadata"]

    assert metadata["constitutional_probe"] is True
    assert metadata["constitutional_probe_source"] == "core.runtime.step_executor"
    assert metadata["runtime_enforcement_mode"] == "audit_only"
    assert metadata["runtime_enforcement_decision"]["mode"] == "audit_only"
    assert metadata["transition_constitution"]["transition_evidence"]


def test_step_executor_dry_run_does_not_block_execution(tmp_path: Path) -> None:
    result = _executor(tmp_path).execute_step(
        {"type": "noop_probe"},
        enforcement_mode="dry_run",
    )
    decision = result["runtime_execution_result"]["metadata"]["runtime_enforcement_decision"]

    assert result["ok"] is True
    assert result["blocked"] is False
    assert decision["mode"] == "dry_run"
    assert decision["blocked"] is False


def test_step_executor_dry_run_reports_would_block_advisory(tmp_path: Path) -> None:
    result = _executor(tmp_path).execute_step(
        {
            "type": "noop_probe",
            "constitutional_probe_from_status": "verified",
            "constitutional_probe_to_status": "running",
        },
        enforcement_mode="dry_run",
    )
    decision = result["runtime_execution_result"]["metadata"]["runtime_enforcement_decision"]

    assert result["ok"] is True
    assert result["blocked"] is False
    assert decision["classification"] == "block_recommended"
    assert decision["would_block"] is True


def test_runtime_execution_result_abi_accepts_probe_metadata() -> None:
    from core.runtime.runtime_execution_result import RuntimeExecutionResult

    payload = RuntimeExecutionResult.from_runtime_mapping(
        {
            "ok": True,
            "metadata": {
                "constitutional_probe": True,
                "runtime_enforcement_mode": "audit_only",
            },
        }
    ).to_dict()

    assert payload["ok"] is True
    assert payload["executed"] is True
    assert payload["metadata"]["constitutional_probe"] is True
    assert payload["metadata"]["runtime_enforcement_mode"] == "audit_only"


def test_forbidden_layers_remain_unwired_from_main_execution_probe() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        root / "core/tasks/scheduler.py",
        root / "core/agent/agent_loop.py",
        root / "core/runtime/repair_transaction_execution_bridge.py",
        root / "app.py",
        root / "services/system_boot.py",
    ]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            forbidden.extend(
                path
                for path in directory.rglob("*.py")
                if "__pycache__" not in path.parts
            )

    markers = (
        "RuntimeEnforcementMode",
        "step_executor_constitutional_probe",
        "_zero_v7330_attach_constitutional_probe",
    )
    for path in forbidden:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
