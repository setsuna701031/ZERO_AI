from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_context as context_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_bootstrap import (
    create_runtime_bootstrap,
    validate_runtime_bootstrap,
)
from core.runtime.aer_runtime_context import (
    create_runtime_context,
    runtime_context_to_summary,
    validate_runtime_context,
)
from core.runtime.aer_runtime_intake import create_runtime_intake


CONTEXT_CONTRACT = "aer.runtime_context.v2"
EXPECTED_CONTEXT_KEYS = {
    "contract",
    "outcome",
    "operator_handoff",
    "valid",
    "errors",
}
EXPECTED_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible upstream result",
    "operator_handoff": "minimal upstream operator intent summary",
    "valid": "structural validity of this context",
    "errors": "structural validation errors",
}


def make_runtime_bootstrap(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-102",
        decision_type=decision_type,
        decision_reason="runtime context test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-102",
        plan_type=plan_type,
        plan_reason="runtime context test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    operator_state = create_operator_state(
        composition_summary=compose_operator_flow(decision, plan)
    )
    handoff = create_operator_handoff(operator_state=operator_state)
    intake = create_runtime_intake(operator_handoff=handoff)
    return create_runtime_bootstrap(runtime_intake=intake)


def expected_operator_handoff() -> dict:
    return {
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


def test_create_runtime_context_projects_minimal_public_context() -> None:
    runtime_bootstrap = make_runtime_bootstrap()

    context = create_runtime_context(runtime_bootstrap=runtime_bootstrap)

    assert context == {
        "contract": CONTEXT_CONTRACT,
        "outcome": "continue",
        "operator_handoff": expected_operator_handoff(),
        "valid": True,
        "errors": [],
    }
    assert "runtime_bootstrap" not in context
    assert "runtime_intake" not in context
    assert validate_runtime_context(context)["valid"] is True


def test_create_runtime_context_preserves_valid_bootstrap_outcomes() -> None:
    approval = create_runtime_context(
        runtime_bootstrap=make_runtime_bootstrap("continue", "request_approval")
    )
    stopped = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap("stop", "continue"))
    issue = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_context(issue)["valid"] is True


def test_context_does_not_forward_bootstrap_or_intake_wrapper_fields() -> None:
    runtime_bootstrap = make_runtime_bootstrap()
    runtime_bootstrap["unknown_top_level"] = {"secret": "not forwarded"}
    runtime_bootstrap["runtime_intake"]["unknown_intake"] = {"secret": "not forwarded"}

    context = create_runtime_context(runtime_bootstrap=runtime_bootstrap)

    assert set(context) == EXPECTED_CONTEXT_KEYS
    assert context["valid"] is False
    assert "bootstrap fields must match declared contract" in context["errors"]
    assert "unknown_top_level" not in context
    assert "runtime_bootstrap" not in context
    assert "runtime_intake" not in context
    assert "unknown_intake" not in context["operator_handoff"]
    assert validate_runtime_context(context)["valid"] is False


def test_exported_context_keys_are_exactly_declared_key_set() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())

    assert set(context) == EXPECTED_CONTEXT_KEYS

    context["unexpected"] = "not allowed"
    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "context fields must match declared contract" in result["errors"]


def test_context_field_purposes_are_documented_and_fixed() -> None:
    assert set(context_module._FIELD_PURPOSES) == EXPECTED_CONTEXT_KEYS
    assert context_module._FIELD_PURPOSES == EXPECTED_FIELD_PURPOSES


def test_malformed_bootstrap_maps_to_invalid_context() -> None:
    runtime_bootstrap = make_runtime_bootstrap()
    runtime_bootstrap["outcome"] = "queued"
    runtime_bootstrap["metadata"] = {"opaque": "not forwarded"}

    context = create_runtime_context(runtime_bootstrap=runtime_bootstrap)

    assert set(context) == EXPECTED_CONTEXT_KEYS
    assert context["outcome"] == "issue_reported"
    assert context["valid"] is False
    assert "invalid outcome: queued" in context["errors"]
    assert "metadata" not in context
    assert "runtime_bootstrap" not in context
    assert validate_runtime_context(context)["valid"] is False


def test_create_runtime_context_returns_new_outputs_without_mutating_input() -> None:
    runtime_bootstrap = make_runtime_bootstrap()
    original = copy.deepcopy(runtime_bootstrap)

    context = create_runtime_context(runtime_bootstrap=runtime_bootstrap)
    summary = runtime_context_to_summary(context)
    context["operator_handoff"]["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] = "mutated"
    summary["operator_handoff"]["operator_state"]["composition_summary"]["plan"][
        "plan_id"
    ] = "mutated"

    assert runtime_bootstrap == original
    assert context is not runtime_bootstrap
    assert summary is not context
    assert runtime_bootstrap["runtime_intake"]["operator_handoff"]["operator_state"][
        "composition_summary"
    ]["decision"]["decision_id"] == "decision-1"
    assert runtime_bootstrap["runtime_intake"]["operator_handoff"]["operator_state"][
        "composition_summary"
    ]["plan"]["plan_id"] == "plan-1"


def test_create_runtime_context_reports_non_dict_bootstrap_as_invalid() -> None:
    context = create_runtime_context(runtime_bootstrap=None)

    assert context["outcome"] == "issue_reported"
    assert context["valid"] is False
    assert "payload must be a dict" in context["errors"]
    assert validate_runtime_context(context)["valid"] is False


def test_runtime_context_to_summary_returns_public_fields_only() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["private"] = {"secret": "not exposed"}
    context["operator_handoff"]["private"] = {"secret": "not exposed"}
    context["errors"] = ["not public"]

    summary = runtime_context_to_summary(context)

    assert summary == {
        "outcome": "continue",
        "operator_handoff": expected_operator_handoff(),
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_bootstrap" not in summary
    assert "runtime_intake" not in summary


def test_valid_issue_reported_bootstrap_remains_valid_context() -> None:
    runtime_bootstrap = make_runtime_bootstrap("report_issue", "stop")

    context = create_runtime_context(runtime_bootstrap=runtime_bootstrap)

    assert validate_runtime_bootstrap(runtime_bootstrap)["valid"] is True
    assert runtime_bootstrap["outcome"] == "issue_reported"
    assert context["outcome"] == "issue_reported"
    assert context["valid"] is True
    assert validate_runtime_context(context)["valid"] is True


def test_validate_runtime_context_rejects_non_dict_payload() -> None:
    result = validate_runtime_context(None)

    assert result["valid"] is False
    assert result["contract"] == CONTEXT_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_context_rejects_missing_required_fields() -> None:
    result = validate_runtime_context({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: operator_handoff" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_context_rejects_invalid_contract() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["contract"] = "wrong.contract"

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_context_rejects_invalid_outcome() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["outcome"] = "queued"

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match operator_handoff outcome" in result["errors"]


def test_validate_runtime_context_requires_operator_handoff_dict() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["operator_handoff"] = []

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "operator_handoff must be a dict" in result["errors"]


def test_validate_runtime_context_rejects_non_summary_handoff_shape() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["operator_handoff"]["metadata"] = {"secret": "not allowed"}

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "operator_handoff must match runtime context summary" in result["errors"]


def test_validate_runtime_context_requires_bool_valid() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["valid"] = "yes"

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_context_requires_error_list() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["errors"] = {}

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_context_rejects_valid_context_with_errors() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["errors"] = ["unexpected"]

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "valid runtime context must not include errors" in result["errors"]


def test_validate_runtime_context_rejects_invalid_context_silent_continue() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["valid"] = False
    context["outcome"] = "continue"
    context["errors"] = ["bootstrap invalid"]

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "invalid runtime context must report issue" in result["errors"]
    assert "runtime context contains invalid runtime bootstrap" in result["errors"]


def test_validate_runtime_context_rejects_invalid_context_without_errors() -> None:
    context = create_runtime_context(runtime_bootstrap=make_runtime_bootstrap())
    context["valid"] = False
    context["outcome"] = "issue_reported"
    context["errors"] = []

    result = validate_runtime_context(context)

    assert result["valid"] is False
    assert "invalid runtime context must include errors" in result["errors"]
    assert "runtime context contains invalid runtime bootstrap" in result["errors"]


def test_runtime_context_exposes_only_public_api() -> None:
    assert context_module.__all__ == [
        "create_runtime_context",
        "validate_runtime_context",
        "runtime_context_to_summary",
    ]


def test_runtime_context_uses_only_runtime_bootstrap_contract_helpers() -> None:
    source = inspect.getsource(context_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_bootstrap" in source
    assert "runtime_bootstrap_to_summary" in source
    assert all("operator_handoff" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_runtime_bootstrap" not in line for line in import_lines)
    assert all("create_runtime_intake" not in line for line in import_lines)


def test_runtime_context_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(context_module)

    forbidden_passthrough_tokens = (
        "dict(runtime_bootstrap",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**runtime_bootstrap",
        "**source",
        "\"runtime_bootstrap\":",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_context_avoids_forbidden_imports() -> None:
    source = inspect.getsource(context_module)
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


def test_runtime_context_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(context_module)
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


def test_runtime_context_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(context_module)

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
