from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_projection as projection_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_bootstrap import create_runtime_bootstrap
from core.runtime.aer_runtime_context import create_runtime_context, validate_runtime_context
from core.runtime.aer_runtime_intake import create_runtime_intake
from core.runtime.aer_runtime_projection import (
    create_runtime_projection,
    runtime_projection_to_summary,
    validate_runtime_projection,
)


PROJECTION_CONTRACT = "aer.runtime_projection.v2"
EXPECTED_PROJECTION_KEYS = {
    "contract",
    "outcome",
    "operator_handoff",
    "valid",
    "errors",
}
EXPECTED_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible context result",
    "operator_handoff": "minimal upstream operator intent summary",
    "valid": "structural validity of this projection",
    "errors": "structural validation errors",
}


def make_runtime_context(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-103",
        decision_type=decision_type,
        decision_reason="runtime projection test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-103",
        plan_type=plan_type,
        plan_reason="runtime projection test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    operator_state = create_operator_state(
        composition_summary=compose_operator_flow(decision, plan)
    )
    handoff = create_operator_handoff(operator_state=operator_state)
    intake = create_runtime_intake(operator_handoff=handoff)
    bootstrap = create_runtime_bootstrap(runtime_intake=intake)
    return create_runtime_context(runtime_bootstrap=bootstrap)


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


def test_create_runtime_projection_projects_context_without_wrapper_fields() -> None:
    runtime_context = make_runtime_context()

    projection = create_runtime_projection(runtime_context=runtime_context)

    assert projection == {
        "contract": PROJECTION_CONTRACT,
        "outcome": "continue",
        "operator_handoff": expected_operator_handoff(),
        "valid": True,
        "errors": [],
    }
    assert set(projection) == EXPECTED_PROJECTION_KEYS
    assert "runtime_context" not in projection
    assert "runtime_bootstrap" not in projection
    assert "runtime_intake" not in projection
    assert validate_runtime_projection(projection)["valid"] is True


def test_create_runtime_projection_preserves_valid_context_outcomes() -> None:
    approval = create_runtime_projection(
        runtime_context=make_runtime_context("continue", "request_approval")
    )
    stopped = create_runtime_projection(runtime_context=make_runtime_context("stop", "continue"))
    issue = create_runtime_projection(runtime_context=make_runtime_context("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_projection(issue)["valid"] is True


def test_projection_does_not_forward_unknown_context_fields() -> None:
    runtime_context = make_runtime_context()
    runtime_context["unknown_top_level"] = {"secret": "not forwarded"}
    runtime_context["operator_handoff"]["unknown_handoff"] = {"secret": "not forwarded"}

    projection = create_runtime_projection(runtime_context=runtime_context)

    assert set(projection) == EXPECTED_PROJECTION_KEYS
    assert projection["valid"] is False
    assert "context fields must match declared contract" in projection["errors"]
    assert "unknown_top_level" not in projection
    assert "runtime_context" not in projection
    assert "unknown_handoff" not in projection["operator_handoff"]
    assert validate_runtime_projection(projection)["valid"] is False


def test_exported_projection_keys_are_exactly_declared_key_set() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())

    assert set(projection) == EXPECTED_PROJECTION_KEYS

    projection["unexpected"] = "not allowed"
    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "projection fields must match declared contract" in result["errors"]


def test_projection_field_purposes_are_documented_and_fixed() -> None:
    assert set(projection_module._FIELD_PURPOSES) == EXPECTED_PROJECTION_KEYS
    assert projection_module._FIELD_PURPOSES == EXPECTED_FIELD_PURPOSES


def test_malformed_context_maps_to_invalid_projection() -> None:
    runtime_context = make_runtime_context()
    runtime_context["outcome"] = "queued"
    runtime_context["metadata"] = {"opaque": "not forwarded"}

    projection = create_runtime_projection(runtime_context=runtime_context)

    assert set(projection) == EXPECTED_PROJECTION_KEYS
    assert projection["outcome"] == "issue_reported"
    assert projection["valid"] is False
    assert "invalid outcome: queued" in projection["errors"]
    assert "metadata" not in projection
    assert "runtime_context" not in projection
    assert validate_runtime_projection(projection)["valid"] is False


def test_create_runtime_projection_returns_new_outputs_without_mutating_input() -> None:
    runtime_context = make_runtime_context()
    original = copy.deepcopy(runtime_context)

    projection = create_runtime_projection(runtime_context=runtime_context)
    summary = runtime_projection_to_summary(projection)
    projection["operator_handoff"]["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] = "mutated"
    summary["operator_handoff"]["operator_state"]["composition_summary"]["plan"][
        "plan_id"
    ] = "mutated"

    assert runtime_context == original
    assert projection is not runtime_context
    assert summary is not projection
    assert runtime_context["operator_handoff"]["operator_state"]["composition_summary"][
        "decision"
    ]["decision_id"] == "decision-1"
    assert runtime_context["operator_handoff"]["operator_state"]["composition_summary"][
        "plan"
    ]["plan_id"] == "plan-1"


def test_create_runtime_projection_reports_non_dict_context_as_invalid() -> None:
    projection = create_runtime_projection(runtime_context=None)

    assert projection["outcome"] == "issue_reported"
    assert projection["valid"] is False
    assert "payload must be a dict" in projection["errors"]
    assert validate_runtime_projection(projection)["valid"] is False


def test_runtime_projection_to_summary_returns_public_fields_only() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["private"] = {"secret": "not exposed"}
    projection["operator_handoff"]["private"] = {"secret": "not exposed"}
    projection["errors"] = ["not public"]

    summary = runtime_projection_to_summary(projection)

    assert summary == {
        "outcome": "continue",
        "operator_handoff": expected_operator_handoff(),
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_context" not in summary
    assert "runtime_bootstrap" not in summary
    assert "runtime_intake" not in summary


def test_valid_issue_reported_context_remains_valid_projection() -> None:
    runtime_context = make_runtime_context("report_issue", "stop")

    projection = create_runtime_projection(runtime_context=runtime_context)

    assert validate_runtime_context(runtime_context)["valid"] is True
    assert runtime_context["outcome"] == "issue_reported"
    assert projection["outcome"] == "issue_reported"
    assert projection["valid"] is True
    assert validate_runtime_projection(projection)["valid"] is True


def test_validate_runtime_projection_rejects_non_dict_payload() -> None:
    result = validate_runtime_projection(None)

    assert result["valid"] is False
    assert result["contract"] == PROJECTION_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_projection_rejects_missing_required_fields() -> None:
    result = validate_runtime_projection({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: operator_handoff" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_projection_rejects_invalid_contract() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["contract"] = "wrong.contract"

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_projection_rejects_invalid_outcome() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["outcome"] = "queued"

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match operator_handoff outcome" in result["errors"]


def test_validate_runtime_projection_requires_operator_handoff_dict() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["operator_handoff"] = []

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "operator_handoff must be a dict" in result["errors"]


def test_validate_runtime_projection_rejects_non_summary_handoff_shape() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["operator_handoff"]["metadata"] = {"secret": "not allowed"}

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "operator_handoff must match runtime projection summary" in result["errors"]


def test_validate_runtime_projection_requires_bool_valid() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["valid"] = "yes"

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_projection_requires_error_list() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["errors"] = {}

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_projection_rejects_valid_projection_with_errors() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["errors"] = ["unexpected"]

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "valid runtime projection must not include errors" in result["errors"]


def test_validate_runtime_projection_rejects_invalid_projection_silent_continue() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["valid"] = False
    projection["outcome"] = "continue"
    projection["errors"] = ["context invalid"]

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "invalid runtime projection must report issue" in result["errors"]
    assert "runtime projection contains invalid runtime context" in result["errors"]


def test_validate_runtime_projection_rejects_invalid_projection_without_errors() -> None:
    projection = create_runtime_projection(runtime_context=make_runtime_context())
    projection["valid"] = False
    projection["outcome"] = "issue_reported"
    projection["errors"] = []

    result = validate_runtime_projection(projection)

    assert result["valid"] is False
    assert "invalid runtime projection must include errors" in result["errors"]
    assert "runtime projection contains invalid runtime context" in result["errors"]


def test_runtime_projection_exposes_only_public_api() -> None:
    assert projection_module.__all__ == [
        "create_runtime_projection",
        "validate_runtime_projection",
        "runtime_projection_to_summary",
    ]


def test_runtime_projection_uses_only_runtime_context_contract_helpers() -> None:
    source = inspect.getsource(projection_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_context" in source
    assert "runtime_context_to_summary" in source
    assert all("runtime_bootstrap" not in line for line in import_lines)
    assert all("runtime_intake" not in line for line in import_lines)
    assert all("operator_handoff" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_runtime_context" not in line for line in import_lines)


def test_runtime_projection_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(projection_module)

    forbidden_passthrough_tokens = (
        "dict(runtime_context",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**runtime_context",
        "**source",
        "\"runtime_context\":",
        "\"runtime_bootstrap\":",
        "\"runtime_intake\":",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_projection_avoids_forbidden_imports() -> None:
    source = inspect.getsource(projection_module)
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


def test_runtime_projection_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(projection_module)
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


def test_runtime_projection_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(projection_module)

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
