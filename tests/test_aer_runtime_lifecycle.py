from __future__ import annotations

import copy
import inspect

import core.runtime.aer_runtime_lifecycle as lifecycle_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_handoff import create_operator_handoff
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import create_operator_state
from core.runtime.aer_runtime_activation import create_runtime_activation, validate_runtime_activation
from core.runtime.aer_runtime_bootstrap import create_runtime_bootstrap
from core.runtime.aer_runtime_context import create_runtime_context
from core.runtime.aer_runtime_intake import create_runtime_intake
from core.runtime.aer_runtime_lifecycle import (
    create_runtime_lifecycle,
    runtime_lifecycle_to_summary,
    validate_runtime_lifecycle,
)
from core.runtime.aer_runtime_projection import create_runtime_projection
from core.runtime.aer_runtime_session import create_runtime_session


LIFECYCLE_CONTRACT = "aer.runtime_lifecycle.v2"
EXPECTED_LIFECYCLE_KEYS = {
    "contract",
    "outcome",
    "runtime_lifecycle",
    "valid",
    "errors",
}
EXPECTED_RUNTIME_LIFECYCLE_KEYS = {
    "outcome",
    "runtime_activation",
    "activation_valid",
}
EXPECTED_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible activation result",
    "runtime_lifecycle": "minimal runtime lifecycle intent summary",
    "valid": "structural validity of this lifecycle contract",
    "errors": "structural validation errors",
}
EXPECTED_LIFECYCLE_FIELD_PURPOSES = {
    "outcome": "runtime-visible activation result",
    "runtime_activation": "minimal runtime activation intent summary",
    "activation_valid": "structural validity of the source activation contract",
}


def make_runtime_activation(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-106",
        decision_type=decision_type,
        decision_reason="runtime lifecycle test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-106",
        plan_type=plan_type,
        plan_reason="runtime lifecycle test",
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
    session = create_runtime_session(runtime_projection=projection)
    return create_runtime_activation(runtime_session=session)


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


def expected_runtime_lifecycle() -> dict:
    return {
        "outcome": "continue",
        "runtime_activation": expected_runtime_activation(),
        "activation_valid": True,
    }


def test_create_runtime_lifecycle_projects_activation_without_wrapper_fields() -> None:
    runtime_activation = make_runtime_activation()

    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=runtime_activation)

    assert runtime_lifecycle == {
        "contract": LIFECYCLE_CONTRACT,
        "outcome": "continue",
        "runtime_lifecycle": expected_runtime_lifecycle(),
        "valid": True,
        "errors": [],
    }
    assert set(runtime_lifecycle) == EXPECTED_LIFECYCLE_KEYS
    assert set(runtime_lifecycle["runtime_lifecycle"]) == EXPECTED_RUNTIME_LIFECYCLE_KEYS
    assert "runtime_session" not in runtime_lifecycle
    assert "runtime_projection" not in runtime_lifecycle
    assert "runtime_context" not in runtime_lifecycle
    assert "runtime_bootstrap" not in runtime_lifecycle
    assert "runtime_intake" not in runtime_lifecycle
    assert validate_runtime_lifecycle(runtime_lifecycle)["valid"] is True


def test_create_runtime_lifecycle_preserves_valid_activation_outcomes() -> None:
    approval = create_runtime_lifecycle(
        runtime_activation=make_runtime_activation("continue", "request_approval")
    )
    stopped = create_runtime_lifecycle(runtime_activation=make_runtime_activation("stop", "continue"))
    issue = create_runtime_lifecycle(runtime_activation=make_runtime_activation("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert issue["errors"] == []
    assert validate_runtime_lifecycle(issue)["valid"] is True


def test_lifecycle_does_not_forward_unknown_activation_fields() -> None:
    runtime_activation = make_runtime_activation()
    runtime_activation["unknown_top_level"] = {"secret": "not forwarded"}
    runtime_activation["runtime_activation"]["unknown_activation"] = {"secret": "not forwarded"}
    runtime_activation["runtime_activation"]["runtime_session"]["unknown_session"] = {
        "secret": "not forwarded"
    }

    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=runtime_activation)

    assert set(runtime_lifecycle) == EXPECTED_LIFECYCLE_KEYS
    assert set(runtime_lifecycle["runtime_lifecycle"]) == EXPECTED_RUNTIME_LIFECYCLE_KEYS
    assert runtime_lifecycle["valid"] is False
    assert "runtime activation fields must match declared contract" in runtime_lifecycle["errors"]
    assert "unknown_top_level" not in runtime_lifecycle
    assert "unknown_activation" not in runtime_lifecycle["runtime_lifecycle"]
    assert "unknown_session" not in runtime_lifecycle["runtime_lifecycle"]["runtime_activation"]["runtime_session"]
    assert validate_runtime_lifecycle(runtime_lifecycle)["valid"] is False


def test_exported_lifecycle_keys_are_exactly_declared_key_set() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())

    assert set(runtime_lifecycle) == EXPECTED_LIFECYCLE_KEYS
    assert set(runtime_lifecycle["runtime_lifecycle"]) == EXPECTED_RUNTIME_LIFECYCLE_KEYS

    runtime_lifecycle["unexpected"] = "not allowed"
    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime lifecycle fields must match declared contract" in result["errors"]


def test_runtime_lifecycle_inner_keys_are_exactly_declared_key_set() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["runtime_lifecycle"]["unexpected"] = "not allowed"

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime_lifecycle fields must match declared contract" in result["errors"]


def test_lifecycle_field_purposes_are_documented_and_fixed() -> None:
    assert set(lifecycle_module._FIELD_PURPOSES) == EXPECTED_LIFECYCLE_KEYS
    assert lifecycle_module._FIELD_PURPOSES == EXPECTED_FIELD_PURPOSES
    assert set(lifecycle_module._LIFECYCLE_FIELD_PURPOSES) == EXPECTED_RUNTIME_LIFECYCLE_KEYS
    assert lifecycle_module._LIFECYCLE_FIELD_PURPOSES == EXPECTED_LIFECYCLE_FIELD_PURPOSES


def test_malformed_activation_maps_to_invalid_lifecycle() -> None:
    runtime_activation = make_runtime_activation()
    runtime_activation["outcome"] = "queued"
    runtime_activation["metadata"] = {"opaque": "not forwarded"}

    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=runtime_activation)

    assert set(runtime_lifecycle) == EXPECTED_LIFECYCLE_KEYS
    assert set(runtime_lifecycle["runtime_lifecycle"]) == EXPECTED_RUNTIME_LIFECYCLE_KEYS
    assert runtime_lifecycle["outcome"] == "issue_reported"
    assert runtime_lifecycle["valid"] is False
    assert "invalid outcome: queued" in runtime_lifecycle["errors"]
    assert "metadata" not in runtime_lifecycle
    assert validate_runtime_lifecycle(runtime_lifecycle)["valid"] is False


def test_create_runtime_lifecycle_returns_new_outputs_without_mutating_input() -> None:
    runtime_activation = make_runtime_activation()
    original = copy.deepcopy(runtime_activation)

    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=runtime_activation)
    summary = runtime_lifecycle_to_summary(runtime_lifecycle)
    runtime_lifecycle["runtime_lifecycle"]["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"]["decision"][
        "decision_id"
    ] = "mutated"
    summary["runtime_lifecycle"]["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"]["plan"][
        "plan_id"
    ] = "mutated"

    assert runtime_activation == original
    assert runtime_lifecycle is not runtime_activation
    assert summary is not runtime_lifecycle
    assert runtime_activation["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"][
        "decision"
    ]["decision_id"] == "decision-1"
    assert runtime_activation["runtime_activation"]["runtime_session"]["operator_handoff"]["operator_state"]["composition_summary"][
        "plan"
    ]["plan_id"] == "plan-1"


def test_create_runtime_lifecycle_reports_non_dict_activation_as_invalid() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=None)

    assert runtime_lifecycle["outcome"] == "issue_reported"
    assert runtime_lifecycle["valid"] is False
    assert "payload must be a dict" in runtime_lifecycle["errors"]
    assert validate_runtime_lifecycle(runtime_lifecycle)["valid"] is False


def test_runtime_lifecycle_to_summary_returns_public_fields_only() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["private"] = {"secret": "not exposed"}
    runtime_lifecycle["runtime_lifecycle"]["private"] = {"secret": "not exposed"}
    runtime_lifecycle["runtime_lifecycle"]["runtime_activation"]["private"] = {"secret": "not exposed"}
    runtime_lifecycle["runtime_lifecycle"]["runtime_activation"]["runtime_session"]["private"] = {
        "secret": "not exposed"
    }
    runtime_lifecycle["errors"] = ["not public"]

    summary = runtime_lifecycle_to_summary(runtime_lifecycle)

    assert summary == {
        "outcome": "continue",
        "runtime_lifecycle": expected_runtime_lifecycle(),
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_session" not in summary
    assert "runtime_projection" not in summary
    assert "runtime_context" not in summary
    assert "runtime_bootstrap" not in summary
    assert "runtime_intake" not in summary


def test_valid_issue_reported_activation_remains_valid_lifecycle() -> None:
    runtime_activation = make_runtime_activation("report_issue", "stop")

    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=runtime_activation)

    assert validate_runtime_activation(runtime_activation)["valid"] is True
    assert runtime_activation["outcome"] == "issue_reported"
    assert runtime_lifecycle["outcome"] == "issue_reported"
    assert runtime_lifecycle["valid"] is True
    assert validate_runtime_lifecycle(runtime_lifecycle)["valid"] is True


def test_validate_runtime_lifecycle_rejects_non_dict_payload() -> None:
    result = validate_runtime_lifecycle(None)

    assert result["valid"] is False
    assert result["contract"] == LIFECYCLE_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_runtime_lifecycle_rejects_missing_required_fields() -> None:
    result = validate_runtime_lifecycle({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: runtime_lifecycle" in result["errors"]
    assert "missing required field: valid" in result["errors"]
    assert "missing required field: errors" in result["errors"]


def test_validate_runtime_lifecycle_rejects_invalid_contract() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["contract"] = "wrong.contract"

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "invalid contract" in result["errors"]


def test_validate_runtime_lifecycle_rejects_invalid_outcome() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["outcome"] = "queued"

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match runtime_lifecycle outcome" in result["errors"]


def test_validate_runtime_lifecycle_requires_runtime_lifecycle_dict() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["runtime_lifecycle"] = []

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime_lifecycle must be a dict" in result["errors"]


def test_validate_runtime_lifecycle_rejects_non_summary_activation_shape() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["runtime_lifecycle"]["runtime_activation"]["metadata"] = {
        "secret": "not allowed"
    }

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime_lifecycle runtime_activation must match runtime lifecycle summary" in result["errors"]


def test_validate_runtime_lifecycle_requires_bool_valid() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["valid"] = "yes"

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "valid must be a bool" in result["errors"]


def test_validate_runtime_lifecycle_requires_activation_valid_bool() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["runtime_lifecycle"]["activation_valid"] = "yes"

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime_lifecycle activation_valid must be a bool" in result["errors"]


def test_validate_runtime_lifecycle_requires_activation_valid_to_match_valid() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["runtime_lifecycle"]["activation_valid"] = False

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "runtime_lifecycle activation_valid must match valid" in result["errors"]


def test_validate_runtime_lifecycle_requires_error_list() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["errors"] = {}

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "errors must be a list" in result["errors"]


def test_validate_runtime_lifecycle_rejects_valid_lifecycle_with_errors() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["errors"] = ["unexpected"]

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "valid runtime lifecycle must not include errors" in result["errors"]


def test_validate_runtime_lifecycle_rejects_invalid_lifecycle_silent_continue() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["valid"] = False
    runtime_lifecycle["outcome"] = "continue"
    runtime_lifecycle["errors"] = ["activation invalid"]

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "invalid runtime lifecycle must report issue" in result["errors"]
    assert "runtime lifecycle contains invalid runtime activation" in result["errors"]


def test_validate_runtime_lifecycle_rejects_invalid_lifecycle_without_errors() -> None:
    runtime_lifecycle = create_runtime_lifecycle(runtime_activation=make_runtime_activation())
    runtime_lifecycle["valid"] = False
    runtime_lifecycle["outcome"] = "issue_reported"
    runtime_lifecycle["errors"] = []

    result = validate_runtime_lifecycle(runtime_lifecycle)

    assert result["valid"] is False
    assert "invalid runtime lifecycle must include errors" in result["errors"]
    assert "runtime lifecycle contains invalid runtime activation" in result["errors"]


def test_runtime_lifecycle_exposes_only_public_api() -> None:
    assert lifecycle_module.__all__ == [
        "create_runtime_lifecycle",
        "validate_runtime_lifecycle",
        "runtime_lifecycle_to_summary",
    ]


def test_runtime_lifecycle_uses_only_runtime_activation_contract_helpers() -> None:
    source = inspect.getsource(lifecycle_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_activation" in source
    assert "runtime_activation_to_summary" in source
    assert all("runtime_session" not in line for line in import_lines)
    assert all("runtime_projection" not in line for line in import_lines)
    assert all("runtime_context" not in line for line in import_lines)
    assert all("runtime_bootstrap" not in line for line in import_lines)
    assert all("runtime_intake" not in line for line in import_lines)
    assert all("operator_handoff" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("create_runtime_activation" not in line for line in import_lines)


def test_runtime_lifecycle_has_no_generic_passthrough_behavior() -> None:
    source = inspect.getsource(lifecycle_module)

    forbidden_passthrough_tokens = (
        "dict(runtime_activation",
        "dict(source",
        ".update(",
        "[\"metadata\"]",
        "['metadata']",
        "payload.copy(",
        "source.copy(",
        "**runtime_activation",
        "**source",
        "\"runtime_projection\":",
        "\"runtime_context\":",
        "\"runtime_bootstrap\":",
        "\"runtime_intake\":",
    )
    for token in forbidden_passthrough_tokens:
        assert token not in source


def test_runtime_lifecycle_avoids_forbidden_imports() -> None:
    source = inspect.getsource(lifecycle_module)
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


def test_runtime_lifecycle_has_no_runtime_or_flow_behavior() -> None:
    source = inspect.getsource(lifecycle_module)
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


def test_runtime_lifecycle_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(lifecycle_module)

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
