from __future__ import annotations

import importlib
from pathlib import Path


def _dispatch_bridge():
    module = importlib.import_module("core.runtime.runtime_scheduler_dispatch_bridge")
    return getattr(module, "evaluate_scheduler_dispatch_bridge")


def _handoff_gate():
    module = importlib.import_module("core.runtime.runtime_executor_handoff_gate")
    return getattr(module, "evaluate_executor_handoff_gate")


def _dispatch_admission(work_cursor: str = "cursor-B") -> dict[str, object]:
    return {
        "scheduler_dispatch_admitted": True,
        "source_wake_bridge_id": "wake-bridge-1",
        "admitted_cursor": work_cursor,
        "scheduler_dispatch_started": False,
        "executor_invoked": False,
        "runtime_state_mutated": False,
        "denial_reason": "",
    }


def test_full_controlled_path_reaches_handoff_without_execution() -> None:
    calls: list[dict[str, object]] = []

    def handler(payload: dict[str, object]) -> dict[str, object]:
        calls.append(dict(payload))
        return {"selected_work_id": "work-1"}

    bridge = _dispatch_bridge()(_dispatch_admission(), handler)

    from core.runtime.runtime_runnable_selection_admission import (
        evaluate_runnable_selection_admission,
    )

    selection = evaluate_runnable_selection_admission(bridge)
    handoff = _handoff_gate()(selection)

    assert calls == [
        {
            "source_dispatch_admission_id": "wake-bridge-1",
            "admitted_cursor": "cursor-B",
        }
    ]
    assert bridge["dispatch_bridge_authorized"] is True
    assert bridge["dispatch_handler_called"] is True
    assert bridge["dispatch_result_received"] is True
    assert bridge["selected_work_id"] == "work-1"
    assert bridge["executor_invoked"] is False
    assert bridge["runtime_state_mutated"] is False

    assert selection["runnable_selection_authorized"] is True
    assert selection["selected_work_id"] == "work-1"
    assert selection["executor_invoked"] is False
    assert selection["runtime_state_mutated"] is False

    assert handoff["executor_handoff_authorized"] is True
    assert handoff["handoff_work_id"] == "work-1"
    assert handoff["executor_called"] is False
    assert handoff["execution_started"] is False
    assert handoff["runtime_state_mutated"] is False


def test_dispatch_bridge_accepts_authorized_admission_without_handler() -> None:
    bridge = _dispatch_bridge()(_dispatch_admission())

    assert bridge["dispatch_bridge_authorized"] is True
    assert bridge["dispatch_handler_called"] is False
    assert bridge["dispatch_result_received"] is False
    assert bridge["selected_work_id"] == ""
    assert bridge["executor_invoked"] is False
    assert bridge["runtime_state_mutated"] is False


def test_missing_dispatch_admission_denies_deterministically() -> None:
    first = _dispatch_bridge()(None)
    second = _dispatch_bridge()(None)

    assert first == second
    assert first["dispatch_bridge_authorized"] is False
    assert first["denial_reason"] == "missing_dispatch_admission"
    assert first["executor_invoked"] is False
    assert first["runtime_state_mutated"] is False


def test_rejected_dispatch_admission_denies() -> None:
    admission = _dispatch_admission()
    admission["scheduler_dispatch_admitted"] = False

    bridge = _dispatch_bridge()(admission)

    assert bridge["dispatch_bridge_authorized"] is False
    assert bridge["denial_reason"] == "dispatch_admission_not_authorized"
    assert bridge["executor_invoked"] is False
    assert bridge["runtime_state_mutated"] is False


def test_dispatch_handler_failure_denies_without_runtime_effects() -> None:
    def broken_handler(payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("boom")

    bridge = _dispatch_bridge()(_dispatch_admission(), broken_handler)

    assert bridge["dispatch_bridge_authorized"] is False
    assert bridge["denial_reason"] == "dispatch_handler_failed"
    assert bridge["dispatch_handler_called"] is False
    assert bridge["dispatch_result_received"] is False
    assert bridge["executor_invoked"] is False
    assert bridge["runtime_state_mutated"] is False


def test_missing_runnable_work_denies_selection() -> None:
    bridge = _dispatch_bridge()(_dispatch_admission())

    from core.runtime.runtime_runnable_selection_admission import (
        evaluate_runnable_selection_admission,
    )

    selection = evaluate_runnable_selection_admission(bridge)

    assert selection["runnable_selection_authorized"] is False
    assert selection["denial_reason"] == "missing_selected_work"
    assert selection["executor_invoked"] is False
    assert selection["runtime_state_mutated"] is False


def test_rejected_selection_denies_handoff() -> None:
    rejected = {
        "runnable_selection_authorized": False,
        "selected_work_id": "work-2",
        "source_dispatch_bridge_id": "bridge-1",
        "denial_reason": "blocked",
        "executor_invoked": False,
        "runtime_state_mutated": False,
    }

    handoff = _handoff_gate()(rejected)

    assert handoff["executor_handoff_authorized"] is False
    assert handoff["handoff_work_id"] == "work-2"
    assert handoff["executor_called"] is False
    assert handoff["execution_started"] is False
    assert handoff["runtime_state_mutated"] is False
    assert handoff["denial_reason"] == "runnable_selection_not_authorized"


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls() -> None:
    paths = [
        Path("core/runtime/runtime_scheduler_dispatch_bridge.py"),
        Path("core/runtime/runtime_runnable_selection_admission.py"),
        Path("core/runtime/runtime_executor_handoff_gate.py"),
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

    for path in paths:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in lowered, f"{token!r} is contained in {path}"
