from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_controlled_executor_run_admission import (
    evaluate_controlled_run_admission,
)
from core.runtime.runtime_controlled_executor_run_bridge import (
    evaluate_controlled_run_bridge,
)
from core.runtime.runtime_controlled_executor_result_intake import (
    evaluate_controlled_run_result_intake,
)


def _activation_record(**overrides):
    record = {
        "activation_bridge_authorized": True,
        "activation_bridge_id": "activation-1",
        "activation_work_id": "work-1",
    }
    record.update(overrides)
    return record


def test_full_controlled_run_path_reaches_result_intake_without_runtime_mutation():
    admission = evaluate_controlled_run_admission(_activation_record())

    captured = []

    def handler(payload):
        captured.append(payload)
        return {"run_result_id": "result-1", "run_status": "finished"}

    bridge = evaluate_controlled_run_bridge(admission, run_handler=handler)
    intake = evaluate_controlled_run_result_intake(bridge)

    assert admission["controlled_run_admitted"] is True
    assert admission["run_started"] is False
    assert admission["runtime_state_mutated"] is False

    assert captured == [
        {"run_work_id": "work-1", "source_run_admission_id": "activation-1"}
    ]
    assert bridge["controlled_run_bridge_authorized"] is True
    assert bridge["run_handler_called"] is True
    assert bridge["run_result_received"] is True
    assert bridge["executor_called"] is False
    assert bridge["runtime_state_mutated"] is False

    assert intake["result_intake_authorized"] is True
    assert intake["run_result_id"] == "result-1"
    assert intake["progress_apply_requested"] is False
    assert intake["cursor_advanced"] is False
    assert intake["runtime_state_mutated"] is False


def test_missing_activation_denies_run_admission():
    record = evaluate_controlled_run_admission(None)
    assert record["controlled_run_admitted"] is False
    assert record["denial_reason"] == "missing_activation_record"
    assert record["run_started"] is False


def test_rejected_activation_denies_run_admission_deterministically():
    record = evaluate_controlled_run_admission(
        _activation_record(activation_bridge_authorized=False)
    )
    again = evaluate_controlled_run_admission(
        _activation_record(activation_bridge_authorized=False)
    )
    assert record == again
    assert record["denial_reason"] == "activation_not_authorized"


def test_missing_work_id_denies_run_admission():
    record = evaluate_controlled_run_admission(_activation_record(activation_work_id=""))
    assert record["controlled_run_admitted"] is False
    assert record["denial_reason"] == "missing_run_work_id"


def test_missing_run_admission_denies_bridge():
    record = evaluate_controlled_run_bridge(None)
    assert record["controlled_run_bridge_authorized"] is False
    assert record["denial_reason"] == "missing_run_admission_record"
    assert record["executor_called"] is False


def test_rejected_run_admission_denies_bridge():
    admission = evaluate_controlled_run_admission(
        _activation_record(activation_bridge_authorized=False)
    )
    record = evaluate_controlled_run_bridge(admission)
    assert record["controlled_run_bridge_authorized"] is False
    assert record["denial_reason"] == "run_admission_not_authorized"
    assert record["run_handler_called"] is False


def test_handler_failure_denies_bridge_without_runtime_mutation():
    admission = evaluate_controlled_run_admission(_activation_record())

    def handler(payload):
        raise RuntimeError("boom")

    record = evaluate_controlled_run_bridge(admission, run_handler=handler)
    assert record["controlled_run_bridge_authorized"] is False
    assert record["run_handler_called"] is True
    assert record["run_result_received"] is False
    assert record["executor_called"] is False
    assert record["runtime_state_mutated"] is False
    assert record["denial_reason"] == "run_handler_failed:RuntimeError"


def test_missing_result_denies_result_intake():
    admission = evaluate_controlled_run_admission(_activation_record())
    bridge = evaluate_controlled_run_bridge(admission)
    record = evaluate_controlled_run_result_intake(bridge)
    assert record["result_intake_authorized"] is False
    assert record["denial_reason"] == "missing_run_result"
    assert record["progress_apply_requested"] is False
    assert record["cursor_advanced"] is False


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls():
    files = [
        Path("core/runtime/runtime_controlled_executor_run_admission.py"),
        Path("core/runtime/runtime_controlled_executor_run_bridge.py"),
        Path("core/runtime/runtime_controlled_executor_result_intake.py"),
    ]
    forbidden = [
        "import scheduler",
        "from scheduler",
        "import executor",
        "from executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "progress_memory",
        "run_one_step",
        ".run(",
    ]
    for path in files:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in lowered, f"{token!r} is contained in {path}"
