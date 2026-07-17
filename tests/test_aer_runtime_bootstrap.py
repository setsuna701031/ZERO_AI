from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_bootstrap as bootstrap_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_bootstrap import (
    create_runtime_bootstrap,
    runtime_bootstrap_to_summary,
    validate_runtime_bootstrap,
)
from core.runtime.aer_runtime_intake import create_runtime_intake, validate_runtime_intake


BOOTSTRAP_CONTRACT = "aer.runtime_bootstrap.v2"
EXPECTED_BOOTSTRAP_KEYS = {
    "contract",
    "outcome",
    "runtime_intake",
    "valid",
    "errors",
}


def make_runtime_intake(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-101",
        decision_type=decision_type,
        decision_reason="runtime bootstrap test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-101",
        plan_type=plan_type,
        plan_reason="runtime bootstrap test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    operator_state = create_operator_state(
        composition_summary=compose_operator_flow(decision, plan)
    )
    handoff = create_operator_handoff(operator_state=operator_state)
    return create_runtime_intake(operator_handoff=handoff)


def test_create_runtime_bootstrap_wraps_runtime_intake_summary() -> None:
    runtime_intake = make_runtime_intake()

    bootstrap = create_runtime_bootstrap(runtime_intake=runtime_intake)

    assert bootstrap == {
        "contract": BOOTSTRAP_CONTRACT,
        "outcome": "continue",
        "runtime_intake": {
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
        },
        "valid": True,
        "errors": [],
    }
    assert validate_runtime_bootstrap(bootstrap)["valid"] is True


def test_create_runtime_bootstrap_preserves_valid_intake_outcomes() -> None:
    approval = create_runtime_bootstrap(
        runtime_intake=make_runtime_intake("continue", "request_approval")
    )
    stopped = create_runtime_bootstrap(runtime_intake=make_runtime_intake("stop", "continue"))
    issue = create_runtime_bootstrap(runtime_intake=make_runtime_intake("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_bootstrap(issue)["valid"] is True


def test_unknown_fields_from_runtime_intake_are_dropped_but_invalidate_bootstrap() -> None:
    runtime_intake = make_runtime_intake()
    runtime_intake["unknown_top_level"] = {"secret": "not forwarded"}
    runtime_intake["operator_handoff"]["unknown_handoff"] = {"secret": "not forwarded"}

    bootstrap = create_runtime_bootstrap(runtime_intake=runtime_intake)

    assert set(bootstrap) == EXPECTED_BOOTSTRAP_KEYS
    assert bootstrap["valid"] is False
    assert "intake fields must match declared contract" in bootstrap["errors"]
    assert "unknown_top_level" not in bootstrap
    assert "unknown_top_level" not in bootstrap["runtime_intake"]
    assert "unknown_handoff" not in bootstrap["runtime_intake"]["operator_handoff"]
    assert validate_runtime_bootstrap(bootstrap)["valid"] is False


def test_exported_bootstrap_keys_are_exactly_declared_key_set() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())

    assert set(bootstrap) == EXPECTED_BOOTSTRAP_KEYS

    bootstrap["unexpected"] = "not allowed"
    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "bootstrap fields must match declared contract" in result["errors"]


def test_malformed_intake_maps_to_invalid_bootstrap() -> None:
    runtime_intake = make_runtime_intake()
    runtime_intake["outcome"] = "queued"
    runtime_intake["metadata"] = {"opaque": "not forwarded"}

    bootstrap = create_runtime_bootstrap(runtime_intake=runtime_intake)

    assert set(bootstrap) == EXPECTED_BOOTSTRAP_KEYS
    assert bootstrap["outcome"] == "issue_reported"
    assert bootstrap["valid"] is False
    assert "invalid outcome: queued" in bootstrap["errors"]
    assert "metadata" not in bootstrap
    assert "metadata" not in bootstrap["runtime_intake"]
    assert validate_runtime_bootstrap(bootstrap)["valid"] is False


def test_create_runtime_bootstrap_returns_new_outputs_without_mutating_input() -> None:
    runtime_intake = make_runtime_intake()
    original = copy.deepcopy(runtime_intake)

    bootstrap = create_runtime_bootstrap(runtime_intake=runtime_intake)
    summary = runtime_bootstrap_to_summary(bootstrap)
    bootstrap["runtime_intake"]["operator_handoff"]["operator_state"]["composition_summary"][
        "decision"
    ]["decision_id"] = "mutated"
    summary["runtime_intake"]["operator_handoff"]["operator_state"]["composition_summary"][
        "plan"
    ]["plan_id"] = "mutated"

    assert runtime_intake == original
    assert bootstrap is not runtime_intake
    assert summary is not bootstrap
    assert runtime_intake["operator_handoff"]["operator_state"]["composition_summary"][
        "decision"
    ]["decision_id"] == "decision-1"
    assert runtime_intake["operator_handoff"]["operator_state"]["composition_summary"][
        "plan"
    ]["plan_id"] == "plan-1"


def test_create_runtime_bootstrap_reports_non_dict_intake_as_invalid() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=None)

    assert bootstrap["outcome"] == "issue_reported"
    assert bootstrap["valid"] is False
    assert "payload must be a dict" in bootstrap["errors"]
    assert validate_runtime_bootstrap(bootstrap)["valid"] is False


def test_runtime_bootstrap_to_summary_returns_public_fields_only() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["private"] = {"secret": "not exposed"}
    bootstrap["runtime_intake"]["private"] = {"secret": "not exposed"}
    bootstrap["errors"] = ["not public"]

    summary = runtime_bootstrap_to_summary(bootstrap)

    assert summary == {
        "outcome": "continue",
        "runtime_intake": {
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
        },
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary


def test_valid_issue_reported_intake_remains_valid_bootstrap() -> None:
    runtime_intake = make_runtime_intake("report_issue", "stop")

    bootstrap = create_runtime_bootstrap(runtime_intake=runtime_intake)

    assert validate_runtime_intake(runtime_intake)["valid"] is True
    assert runtime_intake["outcome"] == "issue_reported"
    assert bootstrap["outcome"] == "issue_reported"
    assert bootstrap["valid"] is True
    assert validate_runtime_bootstrap(bootstrap)["valid"] is True


def test_validate_runtime_bootstrap_rejects_non_dict_payload() -> None:
    result = validate_runtime_bootstrap(None)

    assert result["valid"] is False
    assert result["contract"] == BOOTSTRAP_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_bootstrap_rejects_missing_required_fields() -> None:
    result = validate_runtime_bootstrap({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: runtime_intake" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_bootstrap_rejects_invalid_contract() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["contract"] = "wrong.contract"

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_bootstrap_rejects_invalid_outcome() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["outcome"] = "queued"

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match runtime_intake outcome" in result["errors"]


def test_validate_runtime_bootstrap_requires_runtime_intake_dict() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["runtime_intake"] = []

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "runtime_intake must be a dict" in result["errors"]


def test_validate_runtime_bootstrap_rejects_non_summary_intake_shape() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["runtime_intake"]["operator_handoff"]["metadata"] = {"secret": "not allowed"}

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "runtime_intake must match runtime intake summary" in result["errors"]


def test_validate_runtime_bootstrap_requires_bool_valid() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["valid"] = "yes"

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_bootstrap_requires_error_list() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["errors"] = {}

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_bootstrap_rejects_valid_bootstrap_with_errors() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["errors"] = ["unexpected"]

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "valid runtime bootstrap must not include errors" in result["errors"]


def test_validate_runtime_bootstrap_rejects_invalid_bootstrap_silent_continue() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["valid"] = False
    bootstrap["outcome"] = "continue"
    bootstrap["errors"] = ["intake invalid"]

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "invalid runtime bootstrap must report issue" in result["errors"]
    assert "runtime bootstrap contains invalid runtime intake" in result["errors"]


def test_validate_runtime_bootstrap_rejects_invalid_bootstrap_without_errors() -> None:
    bootstrap = create_runtime_bootstrap(runtime_intake=make_runtime_intake())
    bootstrap["valid"] = False
    bootstrap["outcome"] = "issue_reported"
    bootstrap["errors"] = []

    result = validate_runtime_bootstrap(bootstrap)

    assert result["valid"] is False
    assert "invalid runtime bootstrap must include errors" in result["errors"]
    assert "runtime bootstrap contains invalid runtime intake" in result["errors"]


def test_runtime_bootstrap_exposes_only_public_api() -> None:
    assert bootstrap_module.__all__ == [
        "create_runtime_bootstrap",
        "validate_runtime_bootstrap",
        "runtime_bootstrap_to_summary",
    ]


def test_runtime_bootstrap_uses_only_runtime_intake_contract_helpers() -> None:
    source = inspect.getsource(bootstrap_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_intake" in source
    assert "runtime_intake_to_summary" in source
    assert all("operator_handoff" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_runtime_intake" not in line for line in import_lines)


def test_runtime_bootstrap_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(bootstrap_module)

    forbidden_passthrough_tokens = (
        "dict(runtime_intake",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**runtime_intake",
        "**source",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_bootstrap_avoids_forbidden_imports() -> None:
    source = inspect.getsource(bootstrap_module)
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


def test_runtime_bootstrap_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(bootstrap_module)
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
        "runtime_object",
        "runtime_instance",
        "construct",
        "inject",
        "dependency",
        "resolve",
        "service",
        "workspace",
        "filesystem",
        "repository",
        "config",
        "environment",
        "plugin",
        "initialize",
        "callback",
        "binding",
        "execution_mode",
        "execution_policy",
        "retry_policy",
        "timeout",
        "priority",
        "scheduling",
        "queue",
        "worker",
        "executor",
        "resource_class",
        "concurrency",
        "parallelism",
        "supported_features",
        "supported_capabilities",
        "capability_flags",
        "runtime_capabilities",
        "feature_negotiation",
        "compatibility_matrix",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_runtime_bootstrap_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(bootstrap_module)

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
