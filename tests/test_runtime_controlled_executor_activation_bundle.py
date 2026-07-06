from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_executor_activation_admission import (
    evaluate_executor_activation_admission,
)
from core.runtime.runtime_executor_activation_bridge import (
    evaluate_executor_activation_bridge,
)
from core.runtime.runtime_executor_result_intake_gate import (
    evaluate_executor_result_intake,
)


def _handoff_record(**overrides):
    record = {
        "executor_handoff_authorized": True,
        "handoff_work_id": "work-1577",
        "source_selection_id": "selection-1577",
        "executor_called": False,
        "execution_started": False,
        "runtime_state_mutated": False,
    }
    record.update(overrides)
    return record


def test_full_controlled_executor_activation_path_authorizes_result_intake_without_execution():
    calls = []

    def handler(payload):
        calls.append(payload)
        return {"status": "accepted", "handler": "activation-only"}

    admission = evaluate_executor_activation_admission(_handoff_record()).to_dict()
    bridge = evaluate_executor_activation_bridge(admission, handler).to_dict()
    intake = evaluate_executor_result_intake(bridge).to_dict()

    assert admission["executor_activation_admitted"] is True
    assert admission["executor_called"] is False
    assert admission["execution_started"] is False
    assert admission["runtime_state_mutated"] is False

    assert bridge["executor_activation_bridge_authorized"] is True
    assert bridge["activation_handler_called"] is True
    assert bridge["activation_result_received"] is True
    assert bridge["execution_started"] is False
    assert bridge["runtime_state_mutated"] is False

    assert calls == [
        {
            "handoff_work_id": "work-1577",
            "source_activation_admission_id": "selection-1577",
        }
    ]

    assert intake["executor_result_intake_authorized"] is True
    assert intake["result_accepted"] is True
    assert intake["terminal_status"] == "accepted"
    assert intake["execution_started"] is False
    assert intake["runtime_state_mutated"] is False


def test_missing_handoff_denies_activation_admission_deterministically():
    record = evaluate_executor_activation_admission(None).to_dict()

    assert record["executor_activation_admitted"] is False
    assert record["denial_reason"] == "missing_executor_handoff_record"
    assert record["executor_called"] is False
    assert record["execution_started"] is False


def test_rejected_handoff_denies_activation_admission():
    record = evaluate_executor_activation_admission(
        _handoff_record(executor_handoff_authorized=False)
    ).to_dict()

    assert record["executor_activation_admitted"] is False
    assert record["denial_reason"] == "executor_handoff_not_authorized"


def test_missing_handoff_work_id_denies_activation_admission():
    record = evaluate_executor_activation_admission(
        _handoff_record(handoff_work_id="")
    ).to_dict()

    assert record["executor_activation_admitted"] is False
    assert record["denial_reason"] == "missing_handoff_work_id"


def test_activation_bridge_denies_missing_or_rejected_admission():
    missing = evaluate_executor_activation_bridge(None).to_dict()
    rejected = evaluate_executor_activation_bridge(
        {"executor_activation_admitted": False, "handoff_work_id": "work-1577"}
    ).to_dict()

    assert missing["executor_activation_bridge_authorized"] is False
    assert missing["denial_reason"] == "missing_executor_activation_admission_record"
    assert rejected["executor_activation_bridge_authorized"] is False
    assert rejected["denial_reason"] == "executor_activation_not_admitted"


def test_activation_bridge_handler_failure_is_deterministic_and_no_execution_starts():
    def handler(_payload):
        raise RuntimeError("boom")

    admission = evaluate_executor_activation_admission(_handoff_record()).to_dict()
    bridge = evaluate_executor_activation_bridge(admission, handler).to_dict()

    assert bridge["executor_activation_bridge_authorized"] is False
    assert bridge["activation_handler_called"] is True
    assert bridge["activation_result_received"] is False
    assert bridge["denial_reason"] == "executor_activation_handler_failed"
    assert bridge["execution_started"] is False
    assert bridge["runtime_state_mutated"] is False


def test_result_intake_denies_missing_rejected_or_resultless_bridge():
    missing = evaluate_executor_result_intake(None).to_dict()
    rejected = evaluate_executor_result_intake(
        {"executor_activation_bridge_authorized": False, "handoff_work_id": "work-1577"}
    ).to_dict()
    resultless = evaluate_executor_result_intake(
        {
            "executor_activation_bridge_authorized": True,
            "handoff_work_id": "work-1577",
            "source_activation_admission_id": "selection-1577",
            "activation_result_received": False,
        }
    ).to_dict()

    assert missing["executor_result_intake_authorized"] is False
    assert missing["denial_reason"] == "missing_executor_activation_bridge_record"
    assert rejected["executor_result_intake_authorized"] is False
    assert rejected["denial_reason"] == "executor_activation_bridge_not_authorized"
    assert resultless["executor_result_intake_authorized"] is False
    assert resultless["denial_reason"] == "missing_activation_result"


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls():
    files = [
        Path("core/runtime/runtime_executor_activation_admission.py"),
        Path("core/runtime/runtime_executor_activation_bridge.py"),
        Path("core/runtime/runtime_executor_result_intake_gate.py"),
    ]
    forbidden = [
        "import scheduler",
        "from scheduler",
        "import task_runner",
        "from task_runner",
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
