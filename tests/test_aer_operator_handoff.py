from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_handoff as handoff_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import (
    create_operator_handoff,
    operator_handoff_to_summary,
    validate_operator_handoff,
)
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state


HANDOFF_CONTRACT = "aer.operator_handoff.v2"
EXPECTED_HANDOFF_KEYS = {
    "contract",
    "outcome",
    "operator_state",
    "state_valid",
    "errors",
}


def make_operator_state(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-98",
        decision_type=decision_type,
        decision_reason="operator handoff test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-98",
        plan_type=plan_type,
        plan_reason="operator handoff test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    return create_operator_state(composition_summary=compose_operator_flow(decision, plan))


def test_create_operator_handoff_wraps_operator_state_summary() -> None:
    operator_state = make_operator_state()

    handoff = create_operator_handoff(operator_state=operator_state)

    assert handoff == {
        "contract": HANDOFF_CONTRACT,
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
        "errors": [],
    }
    assert validate_operator_handoff(handoff)["ok"] is True


def test_create_operator_handoff_preserves_valid_operator_state_outcomes() -> None:
    approval = create_operator_handoff(
        operator_state=make_operator_state("continue", "request_approval")
    )
    stopped = create_operator_handoff(operator_state=make_operator_state("stop", "continue"))
    issue = create_operator_handoff(operator_state=make_operator_state("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["state_valid"] is True
    assert stopped["state_valid"] is True
    assert issue["state_valid"] is True


def test_create_operator_handoff_normalizes_operator_state_to_public_summary() -> None:
    operator_state = make_operator_state()
    operator_state["private"] = {"secret": "not exposed"}
    operator_state["composition_summary"]["private"] = {"secret": "not exposed"}

    handoff = create_operator_handoff(operator_state=operator_state)

    assert "private" not in handoff["operator_state"]
    assert "private" not in handoff["operator_state"]["composition_summary"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_unknown_fields_from_operator_state_are_dropped() -> None:
    operator_state = make_operator_state()
    operator_state["unknown_top_level"] = {"secret": "not forwarded"}
    operator_state["composition_summary"]["unknown_composition"] = {"secret": "not forwarded"}
    operator_state["composition_summary"]["decision"]["unknown_decision"] = "not forwarded"
    operator_state["composition_summary"]["plan"]["unknown_plan"] = "not forwarded"

    handoff = create_operator_handoff(operator_state=operator_state)

    assert set(handoff) == EXPECTED_HANDOFF_KEYS
    assert "unknown_top_level" not in handoff
    assert "unknown_top_level" not in handoff["operator_state"]
    assert "unknown_composition" not in handoff["operator_state"]["composition_summary"]
    assert "unknown_decision" not in handoff["operator_state"]["composition_summary"]["decision"]
    assert "unknown_plan" not in handoff["operator_state"]["composition_summary"]["plan"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_opaque_metadata_from_operator_state_is_not_forwarded() -> None:
    operator_state = make_operator_state()
    operator_state["metadata"] = {"opaque": "not forwarded"}
    operator_state["composition_summary"]["metadata"] = {"opaque": "not forwarded"}
    operator_state["composition_summary"]["decision"]["metadata"] = {"opaque": "not forwarded"}
    operator_state["composition_summary"]["plan"]["metadata"] = {"opaque": "not forwarded"}

    handoff = create_operator_handoff(operator_state=operator_state)

    assert "metadata" not in handoff
    assert "metadata" not in handoff["operator_state"]
    assert "metadata" not in handoff["operator_state"]["composition_summary"]
    assert "metadata" not in handoff["operator_state"]["composition_summary"]["decision"]
    assert "metadata" not in handoff["operator_state"]["composition_summary"]["plan"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_exported_handoff_keys_are_exactly_declared_key_set() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())

    assert set(handoff) == EXPECTED_HANDOFF_KEYS

    handoff["unexpected"] = "not allowed"
    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "handoff fields must match declared contract" in result["errors"]


def test_invalid_state_still_maps_only_to_declared_handoff_fields() -> None:
    operator_state = make_operator_state()
    operator_state["outcome"] = "queued"
    operator_state["metadata"] = {"opaque": "not forwarded"}
    operator_state["unknown"] = {"secret": "not forwarded"}

    handoff = create_operator_handoff(operator_state=operator_state)

    assert set(handoff) == EXPECTED_HANDOFF_KEYS
    assert handoff["outcome"] == "issue_reported"
    assert handoff["state_valid"] is False
    assert "metadata" not in handoff
    assert "unknown" not in handoff
    assert "metadata" not in handoff["operator_state"]
    assert "unknown" not in handoff["operator_state"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_create_operator_handoff_returns_new_outputs_without_mutating_input() -> None:
    operator_state = make_operator_state()
    original = copy.deepcopy(operator_state)

    handoff = create_operator_handoff(operator_state=operator_state)
    summary = operator_handoff_to_summary(handoff)
    handoff["operator_state"]["composition_summary"]["decision"]["decision_id"] = "mutated"
    summary["operator_state"]["composition_summary"]["plan"]["plan_id"] = "mutated"

    assert operator_state == original
    assert handoff is not operator_state
    assert summary is not handoff
    assert operator_state["composition_summary"]["decision"]["decision_id"] == "decision-1"
    assert operator_state["composition_summary"]["plan"]["plan_id"] == "plan-1"


def test_create_operator_handoff_reports_invalid_operator_state_as_issue() -> None:
    operator_state = make_operator_state()
    operator_state["outcome"] = "queued"

    handoff = create_operator_handoff(operator_state=operator_state)

    assert handoff["outcome"] == "issue_reported"
    assert handoff["state_valid"] is False
    assert "invalid outcome: queued" in handoff["errors"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_create_operator_handoff_reports_non_dict_operator_state_as_issue() -> None:
    handoff = create_operator_handoff(operator_state=None)

    assert handoff["outcome"] == "issue_reported"
    assert handoff["state_valid"] is False
    assert "payload must be a dict" in handoff["errors"]
    assert validate_operator_handoff(handoff)["ok"] is True


def test_operator_handoff_to_summary_returns_public_fields_only() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["private"] = {"secret": "not exposed"}
    handoff["operator_state"]["private"] = {"secret": "not exposed"}
    handoff["errors"] = ["not public"]

    summary = operator_handoff_to_summary(handoff)

    assert summary == {
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
    }
    assert "private" not in summary
    assert "errors" not in summary


def test_validate_operator_handoff_rejects_non_dict_payload() -> None:
    result = validate_operator_handoff(None)

    assert result["ok"] is False
    assert result["contract"] == HANDOFF_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_operator_handoff_rejects_missing_required_fields() -> None:
    result = validate_operator_handoff({})

    assert result["ok"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: operator_state" in result["errors"]
    assert "missing required field: state_valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_operator_handoff_rejects_invalid_contract() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["contract"] = "wrong.contract"

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_operator_handoff_rejects_invalid_outcome() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["outcome"] = "queued"

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match operator_state outcome" in result["errors"]


def test_validate_operator_handoff_requires_operator_state_dict() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["operator_state"] = []

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "operator_state must be a dict" in result["errors"]


def test_validate_operator_handoff_rejects_non_summary_operator_state_shape() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["operator_state"]["composition_summary"]["metadata"] = {"secret": "not allowed"}

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "operator_state must match operator state summary" in result["errors"]


def test_validate_operator_handoff_requires_bool_state_valid() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["state_valid"] = "yes"

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "state_valid must be a bool" in result["errors"]


def test_validate_operator_handoff_requires_error_list() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["errors"] = {}

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_operator_handoff_rejects_valid_handoff_with_errors() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["errors"] = ["unexpected"]

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "valid handoff must not include errors" in result["errors"]


def test_validate_operator_handoff_rejects_invalid_state_silent_continue() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["state_valid"] = False
    handoff["outcome"] = "continue"
    handoff["errors"] = ["state invalid"]

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "invalid state handoff must report issue" in result["errors"]


def test_validate_operator_handoff_rejects_invalid_state_without_errors() -> None:
    handoff = create_operator_handoff(operator_state=make_operator_state())
    handoff["state_valid"] = False
    handoff["outcome"] = "issue_reported"
    handoff["errors"] = []

    result = validate_operator_handoff(handoff)

    assert result["ok"] is False
    assert "invalid state handoff must include errors" in result["errors"]


def test_operator_handoff_exposes_only_public_api() -> None:
    assert handoff_module.__all__ == [
        "create_operator_handoff",
        "validate_operator_handoff",
        "operator_handoff_to_summary",
    ]


def test_operator_handoff_uses_only_operator_state_contract_helpers() -> None:
    source = inspect.getsource(handoff_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_operator_state" in source
    assert "operator_state_to_summary" in source
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_operator_state" not in line for line in import_lines)


def test_operator_handoff_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(handoff_module)

    forbidden_passthrough_tokens = (
        "dict(operator_state",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**operator_state",
        "**source",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_operator_handoff_avoids_forbidden_imports() -> None:
    source = inspect.getsource(handoff_module)
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


def test_operator_handoff_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(handoff_module)
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
        "time",
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
        "identity",
        "session allocation",
        "allocate_session",
        "operator_session_id",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_operator_handoff_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(handoff_module)

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
