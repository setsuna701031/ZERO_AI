from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_activation as activation_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_activation import (
    create_runtime_activation,
    runtime_activation_to_summary,
    validate_runtime_activation,
)
from core.runtime.aer_runtime_bootstrap import create_runtime_bootstrap
from core.runtime.aer_runtime_context import create_runtime_context
from core.runtime.aer_runtime_intake import create_runtime_intake
from core.runtime.aer_runtime_projection import create_runtime_projection
from core.runtime.aer_runtime_session import create_runtime_session, validate_runtime_session


ACTIVATION_CONTRACT = "aer.runtime_activation.v2"
EXPECTED_ACTIVATION_KEYS = {
    "contract",
    "outcome",
    "runtime_activation",
    "valid",
    "errors",
}
EXPECTED_RUNTIME_ACTIVATION_KEYS = {
    "outcome",
    "runtime_session",
    "session_valid",
}
EXPECTED_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible session result",
    "runtime_activation": "minimal runtime activation intent summary",
    "valid": "structural validity of this activation contract",
    "errors": "structural validation errors",
}
EXPECTED_ACTIVATION_FIELD_PURPOSES = {
    "outcome": "runtime-visible session result",
    "runtime_session": "minimal runtime session intent summary",
    "session_valid": "structural validity of the source session contract",
}


def make_runtime_session(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-105",
        decision_type=decision_type,
        decision_reason="runtime activation test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-105",
        plan_type=plan_type,
        plan_reason="runtime activation test",
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
    context = create_runtime_context(runtime_bootstrap=bootstrap)
    projection = create_runtime_projection(runtime_context=context)
    return create_runtime_session(runtime_projection=projection)


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


def expected_runtime_session() -> dict:
    return {
        "outcome": "continue",
        "operator_handoff": expected_operator_handoff(),
        "projection_valid": True,
    }


def expected_runtime_activation() -> dict:
    return {
        "outcome": "continue",
        "runtime_session": expected_runtime_session(),
        "session_valid": True,
    }


def test_create_runtime_activation_projects_session_without_wrapper_fields() -> None:
    runtime_session = make_runtime_session()

    runtime_activation = create_runtime_activation(runtime_session=runtime_session)

    assert runtime_activation == {
        "contract": ACTIVATION_CONTRACT,
        "outcome": "continue",
        "runtime_activation": expected_runtime_activation(),
        "valid": True,
        "errors": [],
    }
    assert set(runtime_activation) == EXPECTED_ACTIVATION_KEYS
    assert set(runtime_activation["runtime_activation"]) == EXPECTED_RUNTIME_ACTIVATION_KEYS
    assert "runtime_projection" not in runtime_activation
    assert "runtime_context" not in runtime_activation
    assert "runtime_bootstrap" not in runtime_activation
    assert "runtime_intake" not in runtime_activation
    assert validate_runtime_activation(runtime_activation)["valid"] is True


def test_create_runtime_activation_preserves_valid_session_outcomes() -> None:
    approval = create_runtime_activation(
        runtime_session=make_runtime_session("continue", "request_approval")
    )
    stopped = create_runtime_activation(runtime_session=make_runtime_session("stop", "continue"))
    issue = create_runtime_activation(runtime_session=make_runtime_session("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_activation(issue)["valid"] is True


def test_activation_does_not_forward_unknown_session_fields() -> None:
    runtime_session = make_runtime_session()
    runtime_session["unknown_top_level"] = {"secret": "not forwarded"}
    runtime_session["runtime_session"]["unknown_session"] = {"secret": "not forwarded"}
    runtime_session["runtime_session"]["operator_handoff"]["unknown_handoff"] = {
        "secret": "not forwarded"
    }

    runtime_activation = create_runtime_activation(runtime_session=runtime_session)

    assert set(runtime_activation) == EXPECTED_ACTIVATION_KEYS
    assert set(runtime_activation["runtime_activation"]) == EXPECTED_RUNTIME_ACTIVATION_KEYS
    assert runtime_activation["valid"] is False
    assert "runtime session fields must match declared contract" in runtime_activation["errors"]
    assert "unknown_top_level" not in runtime_activation
    assert "runtime_projection" not in runtime_activation
    assert "unknown_session" not in runtime_activation["runtime_activation"]["runtime_session"]
    assert "unknown_handoff" not in runtime_activation["runtime_activation"]["runtime_session"]["operator_handoff"]
    assert validate_runtime_activation(runtime_activation)["valid"] is False


def test_exported_activation_keys_are_exactly_declared_key_set() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())

    assert set(runtime_activation) == EXPECTED_ACTIVATION_KEYS
    assert set(runtime_activation["runtime_activation"]) == EXPECTED_RUNTIME_ACTIVATION_KEYS

    runtime_activation["unexpected"] = "not allowed"
    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime activation fields must match declared contract" in result["errors"]


def test_runtime_activation_inner_keys_are_exactly_declared_key_set() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["runtime_activation"]["unexpected"] = "not allowed"

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime_activation fields must match declared contract" in result["errors"]


def test_activation_field_purposes_are_documented_and_fixed() -> None:
    assert set(activation_module._FIELD_PURPOSES) == EXPECTED_ACTIVATION_KEYS
    assert activation_module._FIELD_PURPOSES == EXPECTED_FIELD_PURPOSES
    assert set(activation_module._ACTIVATION_FIELD_PURPOSES) == EXPECTED_RUNTIME_ACTIVATION_KEYS
    assert activation_module._ACTIVATION_FIELD_PURPOSES == EXPECTED_ACTIVATION_FIELD_PURPOSES


def test_malformed_session_maps_to_invalid_activation() -> None:
    runtime_session = make_runtime_session()
    runtime_session["outcome"] = "queued"
    runtime_session["metadata"] = {"opaque": "not forwarded"}

    runtime_activation = create_runtime_activation(runtime_session=runtime_session)

    assert set(runtime_activation) == EXPECTED_ACTIVATION_KEYS
    assert set(runtime_activation["runtime_activation"]) == EXPECTED_RUNTIME_ACTIVATION_KEYS
    assert runtime_activation["outcome"] == "issue_reported"
    assert runtime_activation["valid"] is False
    assert "invalid outcome: queued" in runtime_activation["errors"]
    assert "metadata" not in runtime_activation
    assert "runtime_session" in runtime_activation["runtime_activation"]
    assert validate_runtime_activation(runtime_activation)["valid"] is False


def test_create_runtime_activation_returns_new_outputs_without_mutating_input() -> None:
    runtime_session = make_runtime_session()
    original = copy.deepcopy(runtime_session)

    runtime_activation = create_runtime_activation(runtime_session=runtime_session)
    summary = runtime_activation_to_summary(runtime_activation)
    runtime_activation["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] = "mutated"
    summary["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"]["plan"][
        "plan_id"
    ] = "mutated"

    assert runtime_session == original
    assert runtime_activation is not runtime_session
    assert summary is not runtime_activation
    assert runtime_session["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"][
        "decision"
    ]["decision_id"] == "decision-1"
    assert runtime_session["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"][
        "plan"
    ]["plan_id"] == "plan-1"


def test_create_runtime_activation_reports_non_dict_session_as_invalid() -> None:
    runtime_activation = create_runtime_activation(runtime_session=None)

    assert runtime_activation["outcome"] == "issue_reported"
    assert runtime_activation["valid"] is False
    assert "payload must be a dict" in runtime_activation["errors"]
    assert validate_runtime_activation(runtime_activation)["valid"] is False


def test_runtime_activation_to_summary_returns_public_fields_only() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["private"] = {"secret": "not exposed"}
    runtime_activation["runtime_activation"]["private"] = {"secret": "not exposed"}
    runtime_activation["runtime_activation"]["runtime_session"]["private"] = {"secret": "not exposed"}
    runtime_activation["runtime_activation"]["runtime_session"]["operator_handoff"]["private"] = {
        "secret": "not exposed"
    }
    runtime_activation["errors"] = ["not public"]

    summary = runtime_activation_to_summary(runtime_activation)

    assert summary == {
        "outcome": "continue",
        "runtime_activation": expected_runtime_activation(),
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_projection" not in summary
    assert "runtime_context" not in summary
    assert "runtime_bootstrap" not in summary
    assert "runtime_intake" not in summary


def test_valid_issue_reported_session_remains_valid_activation() -> None:
    runtime_session = make_runtime_session("report_issue", "stop")

    runtime_activation = create_runtime_activation(runtime_session=runtime_session)

    assert validate_runtime_session(runtime_session)["valid"] is True
    assert runtime_session["outcome"] == "issue_reported"
    assert runtime_activation["outcome"] == "issue_reported"
    assert runtime_activation["valid"] is True
    assert validate_runtime_activation(runtime_activation)["valid"] is True


def test_validate_runtime_activation_rejects_non_dict_payload() -> None:
    result = validate_runtime_activation(None)

    assert result["valid"] is False
    assert result["contract"] == ACTIVATION_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_activation_rejects_missing_required_fields() -> None:
    result = validate_runtime_activation({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: runtime_activation" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_activation_rejects_invalid_contract() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["contract"] = "wrong.contract"

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_activation_rejects_invalid_outcome() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["outcome"] = "queued"

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match runtime_activation outcome" in result["errors"]


def test_validate_runtime_activation_requires_runtime_activation_dict() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["runtime_activation"] = []

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime_activation must be a dict" in result["errors"]


def test_validate_runtime_activation_rejects_non_summary_session_shape() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["runtime_activation"]["runtime_session"]["metadata"] = {
        "secret": "not allowed"
    }

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime_activation runtime_session must match runtime activation summary" in result["errors"]


def test_validate_runtime_activation_requires_bool_valid() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["valid"] = "yes"

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_activation_requires_session_valid_bool() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["runtime_activation"]["session_valid"] = "yes"

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime_activation session_valid must be a bool" in result["errors"]


def test_validate_runtime_activation_requires_session_valid_to_match_valid() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["runtime_activation"]["session_valid"] = False

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "runtime_activation session_valid must match valid" in result["errors"]


def test_validate_runtime_activation_requires_error_list() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["errors"] = {}

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_activation_rejects_valid_activation_with_errors() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["errors"] = ["unexpected"]

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "valid runtime activation must not include errors" in result["errors"]


def test_validate_runtime_activation_rejects_invalid_activation_silent_continue() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["valid"] = False
    runtime_activation["outcome"] = "continue"
    runtime_activation["errors"] = ["session invalid"]

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "invalid runtime activation must report issue" in result["errors"]
    assert "runtime activation contains invalid runtime session" in result["errors"]


def test_validate_runtime_activation_rejects_invalid_activation_without_errors() -> None:
    runtime_activation = create_runtime_activation(runtime_session=make_runtime_session())
    runtime_activation["valid"] = False
    runtime_activation["outcome"] = "issue_reported"
    runtime_activation["errors"] = []

    result = validate_runtime_activation(runtime_activation)

    assert result["valid"] is False
    assert "invalid runtime activation must include errors" in result["errors"]
    assert "runtime activation contains invalid runtime session" in result["errors"]


def test_runtime_activation_exposes_only_public_api() -> None:
    assert activation_module.__all__ == [
        "create_runtime_activation",
        "validate_runtime_activation",
        "runtime_activation_to_summary",
    ]


def test_runtime_activation_uses_only_runtime_session_contract_helpers() -> None:
    source = inspect.getsource(activation_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_session" in source
    assert "runtime_session_to_summary" in source
    assert all("runtime_projection" not in line for line in import_lines)
    assert all("runtime_context" not in line for line in import_lines)
    assert all("runtime_bootstrap" not in line for line in import_lines)
    assert all("runtime_intake" not in line for line in import_lines)
    assert all("operator_handoff" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_runtime_session" not in line for line in import_lines)


def test_runtime_activation_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(activation_module)

    forbidden_passthrough_tokens = (
        "dict(runtime_session",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**runtime_session",
        "**source",
        "\"runtime_projection\":",
        "\"runtime_context\":",
        "\"runtime_bootstrap\":",
        "\"runtime_intake\":",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_activation_avoids_forbidden_imports() -> None:
    source = inspect.getsource(activation_module)
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


def test_runtime_activation_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(activation_module)
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
        "session_id",
        "runtime_identity",
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


def test_runtime_activation_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(activation_module)

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
