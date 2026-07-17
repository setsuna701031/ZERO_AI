from __future__ import annotations

import inspect
import json

import core.runtime.aer_runtime_recovery_marker as recovery_module
from core.runtime.aer_runtime_checkpoint import create_runtime_checkpoint, validate_runtime_checkpoint
from core.runtime.aer_runtime_recovery_marker import (
    create_runtime_recovery_marker,
    runtime_recovery_marker_to_summary,
    validate_runtime_recovery_marker,
)
from tests.test_aer_runtime_checkpoint import make_runtime_lifecycle


RECOVERY_MARKER_CONTRACT = "aer.runtime_recovery_marker.v2"
EXPECTED_RECOVERY_KEYS = {
    "contract",
    "outcome",
    "runtime_recovery_marker",
    "valid",
    "errors",
}
EXPECTED_MARKER_KEYS = {
    "outcome",
    "source_outcome",
    "source_valid",
}


def make_runtime_checkpoint(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    return create_runtime_checkpoint(
        runtime_lifecycle=make_runtime_lifecycle(decision_type, plan_type)
    )


def test_create_runtime_recovery_marker_projects_own_public_contract_only() -> None:
    marker = create_runtime_recovery_marker(runtime_checkpoint=make_runtime_checkpoint())

    assert marker == {
        "contract": RECOVERY_MARKER_CONTRACT,
        "outcome": "continue",
        "runtime_recovery_marker": {
            "outcome": "continue",
            "source_outcome": "continue",
            "source_valid": True,
        },
        "valid": True,
        "errors": [],
    }
    assert set(marker) == EXPECTED_RECOVERY_KEYS
    assert set(marker["runtime_recovery_marker"]) == EXPECTED_MARKER_KEYS
    assert "runtime_checkpoint" not in marker
    assert "runtime_checkpoint" not in marker["runtime_recovery_marker"]
    assert validate_runtime_recovery_marker(marker)["valid"] is True


def test_recovery_marker_preserves_valid_checkpoint_outcomes() -> None:
    approval = create_runtime_recovery_marker(
        runtime_checkpoint=make_runtime_checkpoint("continue", "request_approval")
    )
    stopped = create_runtime_recovery_marker(runtime_checkpoint=make_runtime_checkpoint("stop", "continue"))
    issue = create_runtime_recovery_marker(runtime_checkpoint=make_runtime_checkpoint("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert validate_runtime_recovery_marker(issue)["valid"] is True


def test_recovery_marker_does_not_forward_checkpoint_wrapper_or_view_fields() -> None:
    checkpoint = make_runtime_checkpoint()
    checkpoint["unknown_top_level"] = {"secret": "not forwarded"}
    checkpoint["runtime_checkpoint"]["unknown_checkpoint"] = {"secret": "not forwarded"}

    marker = create_runtime_recovery_marker(runtime_checkpoint=checkpoint)

    assert set(marker) == EXPECTED_RECOVERY_KEYS
    assert set(marker["runtime_recovery_marker"]) == EXPECTED_MARKER_KEYS
    assert marker["valid"] is False
    assert marker["errors"] == ["invalid upstream contract"]
    assert "unknown_top_level" not in marker
    assert "runtime_checkpoint" not in marker
    assert "unknown_checkpoint" not in marker["runtime_recovery_marker"]
    assert validate_runtime_recovery_marker(marker)["valid"] is False


def test_recovery_marker_projection_leak_seal_blocks_checkpoint_names_recursively() -> None:
    checkpoint = make_runtime_checkpoint()
    checkpoint["checkpoint_object"] = {"secret": "not forwarded"}
    checkpoint["runtime_checkpoint"]["checkpoint_payload"] = {"secret": "not forwarded"}

    marker = create_runtime_recovery_marker(runtime_checkpoint=checkpoint)
    encoded = json.dumps(marker, sort_keys=True)

    assert set(marker) == EXPECTED_RECOVERY_KEYS
    assert set(marker["runtime_recovery_marker"]) == EXPECTED_MARKER_KEYS
    assert marker["runtime_recovery_marker"] == {
        "outcome": "issue_reported",
        "source_outcome": "continue",
        "source_valid": False,
    }
    assert "runtime_checkpoint" not in encoded
    assert "checkpoint_object" not in encoded
    assert "checkpoint_payload" not in encoded
    assert "checkpoint_valid" not in encoded
    assert "lifecycle_valid" not in encoded


def test_recovery_marker_internal_checkpoint_changes_only_affect_generic_source_fields() -> None:
    checkpoint = make_runtime_checkpoint()
    checkpoint["runtime_checkpoint"]["source_outcome"] = "stopped"

    marker = create_runtime_recovery_marker(runtime_checkpoint=checkpoint)

    assert marker == {
        "contract": RECOVERY_MARKER_CONTRACT,
        "outcome": "issue_reported",
        "runtime_recovery_marker": {
            "outcome": "issue_reported",
            "source_outcome": "continue",
            "source_valid": False,
        },
        "valid": False,
        "errors": ["invalid upstream contract"],
    }
    assert set(marker["runtime_recovery_marker"]) == EXPECTED_MARKER_KEYS
    assert "runtime_checkpoint" not in json.dumps(marker, sort_keys=True)


def test_runtime_recovery_marker_to_summary_returns_public_fields_only() -> None:
    marker = create_runtime_recovery_marker(runtime_checkpoint=make_runtime_checkpoint())
    marker["private"] = {"secret": "not exposed"}
    marker["runtime_recovery_marker"]["private"] = {"secret": "not exposed"}
    marker["errors"] = ["not public"]

    summary = runtime_recovery_marker_to_summary(marker)

    assert summary == {
        "outcome": "continue",
        "runtime_recovery_marker": {
            "outcome": "continue",
            "source_outcome": "continue",
            "source_valid": True,
        },
        "valid": True,
    }
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_checkpoint" not in summary
    assert "runtime_checkpoint" not in summary["runtime_recovery_marker"]


def test_create_runtime_recovery_marker_reports_non_dict_checkpoint_as_invalid() -> None:
    marker = create_runtime_recovery_marker(runtime_checkpoint=None)

    assert marker["outcome"] == "issue_reported"
    assert marker["valid"] is False
    assert marker["errors"] == ["invalid upstream contract"]
    assert validate_runtime_recovery_marker(marker)["valid"] is False


def test_valid_issue_reported_checkpoint_remains_valid_recovery_marker() -> None:
    checkpoint = make_runtime_checkpoint("report_issue", "stop")
    marker = create_runtime_recovery_marker(runtime_checkpoint=checkpoint)

    assert validate_runtime_checkpoint(checkpoint)["valid"] is True
    assert marker["outcome"] == "issue_reported"
    assert marker["valid"] is True
    assert validate_runtime_recovery_marker(marker)["valid"] is True


def test_validate_runtime_recovery_marker_rejects_malformed_payloads() -> None:
    result = validate_runtime_recovery_marker({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: runtime_recovery_marker" in result["errors"]

    marker = create_runtime_recovery_marker(runtime_checkpoint=make_runtime_checkpoint())
    marker["runtime_recovery_marker"]["unexpected"] = "not allowed"

    result = validate_runtime_recovery_marker(marker)

    assert result["valid"] is False
    assert "runtime_recovery_marker fields must match declared contract" in result["errors"]


def test_recovery_marker_field_purposes_are_documented_and_fixed() -> None:
    assert set(recovery_module._FIELD_PURPOSES) == EXPECTED_RECOVERY_KEYS
    assert set(recovery_module._MARKER_FIELD_PURPOSES) == EXPECTED_MARKER_KEYS


def test_runtime_recovery_marker_exposes_only_public_api() -> None:
    assert recovery_module.__all__ == [
        "create_runtime_recovery_marker",
        "validate_runtime_recovery_marker",
        "runtime_recovery_marker_to_summary",
    ]


def test_runtime_recovery_marker_uses_only_runtime_checkpoint_contract_helpers() -> None:
    source = inspect.getsource(recovery_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_checkpoint" in source
    assert "runtime_checkpoint_to_summary" in source
    assert all("runtime_lifecycle" not in line for line in import_lines)
    assert all("create_runtime_checkpoint" not in line for line in import_lines)


def test_runtime_recovery_marker_has_no_recovery_or_runtime_behavior() -> None:
    source = inspect.getsource(recovery_module)

    forbidden_tokens = (
        "open(",
        "pathlib",
        "os.",
        "save_",
        "load_",
        "write_",
        "persist",
        "store",
        "recover(",
        "resume",
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
