from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_intake as intake_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_intake import (
    create_runtime_intake,
    runtime_intake_to_summary,
    validate_runtime_intake,
)


INTAKE_CONTRACT = "aer.runtime_intake.v2"
EXPECTED_INTAKE_KEYS = {
    "contract",
    "outcome",
    "operator_handoff",
    "valid",
    "errors",
}


def make_operator_handoff(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-99",
        decision_type=decision_type,
        decision_reason="runtime intake test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-99",
        plan_type=plan_type,
        plan_reason="runtime intake test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    operator_state = create_operator_state(
        composition_summary=compose_operator_flow(decision, plan)
    )
    return create_operator_handoff(operator_state=operator_state)


def test_create_runtime_intake_wraps_operator_handoff_summary() -> None:
    operator_handoff = make_operator_handoff()

    intake = create_runtime_intake(operator_handoff=operator_handoff)

    assert intake == {
        "contract": INTAKE_CONTRACT,
        "outcome": "continue",
        "operator_handoff": {
            "outcome": "continue",
            "operator_state": {
                "outcome": "continue",
                "composition_summary": {
                    "outcome": "continue",
                    "decision": {
                        "outcome": "continue",
                        "decision_id": "decision-1",
                        "decision_type": "continue",
                        "status": "proposed",
                    },
                    "plan": {
                        "outcome": "continue",
                        "plan_id": "plan-1",
                        "plan_type": "continue",
                        "status": "proposed",
                    },
                },
            },
            "state_valid": True,
        },
        "valid": True,
        "errors": [],
    }
    assert validate_runtime_intake(intake)["valid"] is True


def test_create_runtime_intake_preserves_valid_handoff_outcomes() -> None:
    approval = create_runtime_intake(
        operator_handoff=make_operator_handoff("continue", "request_approval")
    )
    stopped = create_runtime_intake(operator_handoff=make_operator_handoff("stop", "continue"))
    issue = create_runtime_intake(operator_handoff=make_operator_handoff("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_intake(issue)["valid"] is True


def test_unknown_fields_from_operator_handoff_are_dropped_but_invalidate_intake() -> None:
    operator_handoff = make_operator_handoff()
    operator_handoff["unknown_top_level"] = {"secret": "not forwarded"}
    operator_handoff["operator_state"]["unknown_state"] = {"secret": "not forwarded"}
    operator_handoff["operator_state"]["composition_summary"]["unknown_composition"] = {
        "secret": "not forwarded"
    }

    intake = create_runtime_intake(operator_handoff=operator_handoff)

    assert set(intake) == EXPECTED_INTAKE_KEYS
    assert "unknown_top_level" not in intake
    assert "unknown_top_level" not in intake["operator_handoff"]
    assert "unknown_state" not in intake["operator_handoff"]["operator_state"]
    assert (
        "unknown_composition"
        not in intake["operator_handoff"]["operator_state"]["composition_summary"]
    )
    assert intake["valid"] is False
    assert "handoff fields must match declared contract" in intake["errors"]
    assert validate_runtime_intake(intake)["valid"] is False


def test_exported_intake_keys_are_exactly_declared_key_set() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())

    assert set(intake) == EXPECTED_INTAKE_KEYS

    intake["unexpected"] = "not allowed"
    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "intake fields must match declared contract" in result["errors"]


def test_invalid_handoff_still_maps_only_to_declared_intake_fields() -> None:
    operator_handoff = make_operator_handoff()
    operator_handoff["outcome"] = "queued"
    operator_handoff["metadata"] = {"opaque": "not forwarded"}
    operator_handoff["unknown"] = {"secret": "not forwarded"}

    intake = create_runtime_intake(operator_handoff=operator_handoff)

    assert set(intake) == EXPECTED_INTAKE_KEYS
    assert intake["outcome"] == "issue_reported"
    assert intake["valid"] is False
    assert "invalid outcome: queued" in intake["errors"]
    assert "metadata" not in intake
    assert "unknown" not in intake
    assert "metadata" not in intake["operator_handoff"]
    assert "unknown" not in intake["operator_handoff"]
    assert validate_runtime_intake(intake)["valid"] is False


def test_create_runtime_intake_returns_new_outputs_without_mutating_input() -> None:
    operator_handoff = make_operator_handoff()
    original = copy.deepcopy(operator_handoff)

    intake = create_runtime_intake(operator_handoff=operator_handoff)
    summary = runtime_intake_to_summary(intake)
    intake["operator_handoff"]["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] = "mutated"
    summary["operator_handoff"]["operator_state"]["composition_summary"]["plan"][
        "plan_id"
    ] = "mutated"

    assert operator_handoff == original
    assert intake is not operator_handoff
    assert summary is not intake
    assert operator_handoff["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] == "decision-1"
    assert operator_handoff["operator_state"]["composition_summary"]["plan"]["plan_id"] == "plan-1"


def test_create_runtime_intake_reports_invalid_handoff_as_issue() -> None:
    operator_handoff = make_operator_handoff()
    operator_handoff["outcome"] = "queued"

    intake = create_runtime_intake(operator_handoff=operator_handoff)

    assert intake["outcome"] == "issue_reported"
    assert intake["valid"] is False
    assert "invalid outcome: queued" in intake["errors"]
    assert validate_runtime_intake(intake)["valid"] is False


def test_create_runtime_intake_reports_non_dict_handoff_as_issue() -> None:
    intake = create_runtime_intake(operator_handoff=None)

    assert intake["outcome"] == "issue_reported"
    assert intake["valid"] is False
    assert "payload must be a dict" in intake["errors"]
    assert validate_runtime_intake(intake)["valid"] is False


def test_runtime_intake_to_summary_returns_public_fields_only() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["private"] = {"secret": "not exposed"}
    intake["operator_handoff"]["private"] = {"secret": "not exposed"}
    intake["errors"] = ["not public"]

    summary = runtime_intake_to_summary(intake)

    assert summary == {
        "outcome": "continue",
        "operator_handoff": {
            "outcome": "continue",
            "operator_state": {
                "outcome": "continue",
                "composition_summary": {
                    "outcome": "continue",
                    "decision": {
                        "outcome": "continue",
                        "decision_id": "decision-1",
                        "decision_type": "continue",
                        "status": "proposed",
                    },
                    "plan": {
                        "outcome": "continue",
                        "plan_id": "plan-1",
                        "plan_type": "continue",
                        "status": "proposed",
                    },
                },
            },
            "state_valid": True,
        },
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary


def test_validate_runtime_intake_rejects_non_dict_payload() -> None:
    result = validate_runtime_intake(None)

    assert result["valid"] is False
    assert result["contract"] == INTAKE_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_intake_rejects_missing_required_fields() -> None:
    result = validate_runtime_intake({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: operator_handoff" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_intake_rejects_invalid_contract() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["contract"] = "wrong.contract"

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_intake_rejects_invalid_outcome() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["outcome"] = "queued"

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match operator_handoff outcome" in result["errors"]


def test_validate_runtime_intake_requires_operator_handoff_dict() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["operator_handoff"] = []

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "operator_handoff must be a dict" in result["errors"]


def test_validate_runtime_intake_rejects_non_summary_handoff_shape() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["operator_handoff"]["operator_state"]["metadata"] = {"secret": "not allowed"}

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "operator_handoff must match operator handoff summary" in result["errors"]


def test_validate_runtime_intake_requires_bool_valid() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["valid"] = "yes"

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_intake_requires_error_list() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["errors"] = {}

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_intake_rejects_valid_intake_with_errors() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["errors"] = ["unexpected"]

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "valid runtime intake must not include errors" in result["errors"]


def test_validate_runtime_intake_rejects_invalid_intake_silent_continue() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["valid"] = False
    intake["outcome"] = "continue"
    intake["errors"] = ["handoff invalid"]

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "invalid runtime intake must report issue" in result["errors"]
    assert "runtime intake contains invalid operator handoff" in result["errors"]


def test_validate_runtime_intake_rejects_invalid_intake_without_errors() -> None:
    intake = create_runtime_intake(operator_handoff=make_operator_handoff())
    intake["valid"] = False
    intake["outcome"] = "issue_reported"
    intake["errors"] = []

    result = validate_runtime_intake(intake)

    assert result["valid"] is False
    assert "invalid runtime intake must include errors" in result["errors"]
    assert "runtime intake contains invalid operator handoff" in result["errors"]


def test_runtime_intake_exposes_only_public_api() -> None:
    assert intake_module.__all__ == [
        "create_runtime_intake",
        "validate_runtime_intake",
        "runtime_intake_to_summary",
    ]


def test_runtime_intake_uses_only_handoff_contract_helpers() -> None:
    source = inspect.getsource(intake_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_operator_handoff" in source
    assert "operator_handoff_to_summary" in source
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_operator_handoff" not in line for line in import_lines)
    assert all("create_operator_state" not in line for line in import_lines)


def test_runtime_intake_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(intake_module)

    forbidden_passthrough_tokens = (
        "dict(operator_handoff",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**operator_handoff",
        "**source",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_intake_avoids_forbidden_imports() -> None:
    source = inspect.getsource(intake_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    forbidden_imports = (
        "scheduler",
        "task_runner",
        "operator_loop",
        "persistent_operator",
        "event_log",
        "checkpoint_store",
        "resume",
        "audit_reader",
    )
    for token in forbidden_imports:
        assert all(token not in line for line in import_lines)


def test_runtime_intake_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(intake_module)
    surface = "\n".join(
        line
        for line in source.splitlines()
        if not line.startswith("import ") and not line.startswith("from ")
    )

    forbidden_surface_tokens = (
        "run_",
        "execute",
        "dispatch",
        "task_runtime",
        "runtime_execution",
        "append_",
        "emit_",
        "save_",
        "load_",
        "open(",
        "os.",
        "pathlib",
        "time.",
        "time(",
        "timer",
        "retry",
        "repair",
        "checkpoint",
        "resume",
        "transition",
        "lifecycle",
        "ownership",
        "authority",
        "lease",
        "lock",
        "reservation",
        "permission",
        "recovery",
        "watchdog",
        "runtime_session",
        "session_id",
        "identity",
        "allocate_session",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_runtime_intake_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(intake_module)

    forbidden_surface_tokens = (
        "scheduler",
        "schedule",
        "task_runner",
        "TaskRunner",
        "enqueue",
        "queue",
        "worker",
        "loop",
    )
    for token in forbidden_surface_tokens:
        assert token not in source
