from __future__ import annotations

import copy
import inspect
import json

import core.runtime.aer_runtime_checkpoint as checkpoint_module
from core.runtime.aer_runtime_checkpoint import (
    create_runtime_checkpoint,
    runtime_checkpoint_to_summary,
    validate_runtime_checkpoint,
)
from core.runtime.aer_runtime_lifecycle import create_runtime_lifecycle, validate_runtime_lifecycle
from tests.test_aer_runtime_lifecycle import make_runtime_activation


CHECKPOINT_CONTRACT = "aer.runtime_checkpoint.v2"
EXPECTED_CHECKPOINT_KEYS = {
    "contract",
    "outcome",
    "runtime_checkpoint",
    "valid",
    "errors",
}
EXPECTED_MARKER_KEYS = {
    "outcome",
    "source_outcome",
    "source_valid",
}


def make_runtime_lifecycle(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    return create_runtime_lifecycle(
        runtime_activation=make_runtime_activation(decision_type, plan_type)
    )


def test_create_runtime_checkpoint_projects_public_marker_only() -> None:
    checkpoint = create_runtime_checkpoint(runtime_lifecycle=make_runtime_lifecycle())

    assert checkpoint == {
        "contract": CHECKPOINT_CONTRACT,
        "outcome": "continue",
        "runtime_checkpoint": {
            "outcome": "continue",
            "source_outcome": "continue",
            "source_valid": True,
        },
        "valid": True,
        "errors": [],
    }
    assert set(checkpoint) == EXPECTED_CHECKPOINT_KEYS
    assert set(checkpoint["runtime_checkpoint"]) == EXPECTED_MARKER_KEYS
    assert "runtime_lifecycle" not in checkpoint
    assert validate_runtime_checkpoint(checkpoint)["valid"] is True


def test_create_runtime_checkpoint_preserves_valid_lifecycle_outcomes() -> None:
    approval = create_runtime_checkpoint(
        runtime_lifecycle=make_runtime_lifecycle("continue", "request_approval")
    )
    stopped = create_runtime_checkpoint(runtime_lifecycle=make_runtime_lifecycle("stop", "continue"))
    issue = create_runtime_checkpoint(runtime_lifecycle=make_runtime_lifecycle("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert validate_runtime_checkpoint(issue)["valid"] is True


def test_checkpoint_does_not_forward_lifecycle_wrapper_fields() -> None:
    lifecycle = make_runtime_lifecycle()
    lifecycle["unknown_top_level"] = {"secret": "not forwarded"}
    lifecycle["runtime_lifecycle"]["unknown_lifecycle"] = {"secret": "not forwarded"}

    checkpoint = create_runtime_checkpoint(runtime_lifecycle=lifecycle)

    assert set(checkpoint) == EXPECTED_CHECKPOINT_KEYS
    assert set(checkpoint["runtime_checkpoint"]) == EXPECTED_MARKER_KEYS
    assert checkpoint["valid"] is False
    assert checkpoint["errors"] == ["invalid upstream contract"]
    assert "unknown_top_level" not in checkpoint
    assert "runtime_lifecycle" not in checkpoint
    assert "unknown_lifecycle" not in checkpoint["runtime_checkpoint"]
    assert validate_runtime_checkpoint(checkpoint)["valid"] is False


def test_checkpoint_projection_leak_seal_rejects_lifecycle_names_in_public_payload() -> None:
    lifecycle = make_runtime_lifecycle()
    lifecycle["runtime_lifecycle"]["runtime_activation"]["leaked_runtime_lifecycle"] = {
        "secret": "not forwarded"
    }

    checkpoint = create_runtime_checkpoint(runtime_lifecycle=lifecycle)
    encoded = json.dumps(checkpoint, sort_keys=True)

    assert set(checkpoint) == EXPECTED_CHECKPOINT_KEYS
    assert set(checkpoint["runtime_checkpoint"]) == EXPECTED_MARKER_KEYS
    assert checkpoint["runtime_checkpoint"] == {
        "outcome": "issue_reported",
        "source_outcome": "continue",
        "source_valid": False,
    }
    assert "leaked_runtime_lifecycle" not in encoded
    assert "runtime_lifecycle" not in encoded
    assert "runtime_activation" not in encoded
    assert "runtime_session" not in encoded


def test_checkpoint_internal_lifecycle_changes_only_affect_generic_source_fields() -> None:
    lifecycle = make_runtime_lifecycle()
    lifecycle["runtime_lifecycle"]["outcome"] = "stopped"

    checkpoint = create_runtime_checkpoint(runtime_lifecycle=lifecycle)

    assert checkpoint == {
        "contract": CHECKPOINT_CONTRACT,
        "outcome": "issue_reported",
        "runtime_checkpoint": {
            "outcome": "issue_reported",
            "source_outcome": "continue",
            "source_valid": False,
        },
        "valid": False,
        "errors": ["invalid upstream contract"],
    }
    assert set(checkpoint["runtime_checkpoint"]) == EXPECTED_MARKER_KEYS


def test_runtime_checkpoint_to_summary_returns_public_fields_only() -> None:
    checkpoint = create_runtime_checkpoint(runtime_lifecycle=make_runtime_lifecycle())
    checkpoint["private"] = {"secret": "not exposed"}
    checkpoint["runtime_checkpoint"]["private"] = {"secret": "not exposed"}
    checkpoint["errors"] = ["not public"]

    summary = runtime_checkpoint_to_summary(checkpoint)

    assert summary == {
        "outcome": "continue",
        "runtime_checkpoint": {
            "outcome": "continue",
            "source_outcome": "continue",
            "source_valid": True,
        },
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_lifecycle" not in summary


def test_create_runtime_checkpoint_returns_new_outputs_without_mutating_input() -> None:
    lifecycle = make_runtime_lifecycle()
    original = copy.deepcopy(lifecycle)

    checkpoint = create_runtime_checkpoint(runtime_lifecycle=lifecycle)
    summary = runtime_checkpoint_to_summary(checkpoint)
    checkpoint["runtime_checkpoint"]["source_outcome"] = "stopped"
    summary["runtime_checkpoint"]["source_outcome"] = "issue_reported"

    assert lifecycle == original
    assert checkpoint is not lifecycle
    assert summary is not checkpoint


def test_create_runtime_checkpoint_reports_non_dict_lifecycle_as_invalid() -> None:
    checkpoint = create_runtime_checkpoint(runtime_lifecycle=None)

    assert checkpoint["outcome"] == "issue_reported"
    assert checkpoint["valid"] is False
    assert checkpoint["errors"] == ["invalid upstream contract"]
    assert validate_runtime_checkpoint(checkpoint)["valid"] is False


def test_validate_runtime_checkpoint_rejects_malformed_payloads() -> None:
    result = validate_runtime_checkpoint({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: runtime_checkpoint" in result["errors"]

    checkpoint = create_runtime_checkpoint(runtime_lifecycle=make_runtime_lifecycle())
    checkpoint["runtime_checkpoint"]["unexpected"] = "not allowed"

    result = validate_runtime_checkpoint(checkpoint)

    assert result["valid"] is False
    assert "runtime_checkpoint fields must match declared contract" in result["errors"]


def test_checkpoint_field_purposes_are_documented_and_fixed() -> None:
    assert set(checkpoint_module._FIELD_PURPOSES) == EXPECTED_CHECKPOINT_KEYS
    assert set(checkpoint_module._CHECKPOINT_FIELD_PURPOSES) == EXPECTED_MARKER_KEYS


def test_valid_issue_reported_lifecycle_remains_valid_checkpoint() -> None:
    lifecycle = make_runtime_lifecycle("report_issue", "stop")
    checkpoint = create_runtime_checkpoint(runtime_lifecycle=lifecycle)

    assert validate_runtime_lifecycle(lifecycle)["valid"] is True
    assert checkpoint["outcome"] == "issue_reported"
    assert checkpoint["valid"] is True
    assert validate_runtime_checkpoint(checkpoint)["valid"] is True


def test_runtime_checkpoint_exposes_only_public_api() -> None:
    assert checkpoint_module.__all__ == [
        "create_runtime_checkpoint",
        "validate_runtime_checkpoint",
        "runtime_checkpoint_to_summary",
    ]


def test_runtime_checkpoint_uses_only_runtime_lifecycle_contract_helpers() -> None:
    source = inspect.getsource(checkpoint_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_lifecycle" in source
    assert "runtime_lifecycle_to_summary" in source
    assert all("runtime_activation" not in line for line in import_lines)
    assert all("runtime_session" not in line for line in import_lines)
    assert all("create_runtime_lifecycle" not in line for line in import_lines)


def test_runtime_checkpoint_has_no_behavior_or_storage_coupling() -> None:
    source = inspect.getsource(checkpoint_module)

    forbidden_tokens = (
        "open(",
        "pathlib",
        "os.",
        "save_",
        "load_",
        "write_",
        "persist",
        "store",
        "execute",
        "dispatch",
        "scheduler",
        "task_runner",
        "operator_loop",
        "runtime_loop",
        "allocate",
        "workspace",
        "repository",
        "config",
        "plugin",
    )
    for token in forbidden_tokens:
        assert token not in source
