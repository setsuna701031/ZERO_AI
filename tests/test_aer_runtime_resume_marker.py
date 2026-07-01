from __future__ import annotations

import inspect
import json

import core.runtime.aer_runtime_resume_marker as resume_module
from core.runtime.aer_runtime_recovery_marker import (
    create_runtime_recovery_marker,
    validate_runtime_recovery_marker,
)
from core.runtime.aer_runtime_resume_marker import (
    create_runtime_resume_marker,
    runtime_resume_marker_to_summary,
    validate_runtime_resume_marker,
)
from tests.test_aer_runtime_recovery_marker import make_runtime_checkpoint


RESUME_MARKER_CONTRACT = "aer.runtime_resume_marker.v2"
RESUME_MARKER_SUMMARY_CONTRACT = "aer.runtime.resume_marker.summary.v1"
EXPECTED_RESUME_KEYS = {
    "contract",
    "outcome",
    "runtime_resume_marker",
    "valid",
    "errors",
}
EXPECTED_MARKER_KEYS = {
    "outcome",
    "source_outcome",
    "source_valid",
}
EXPECTED_SUMMARY_KEYS = {
    "contract",
    "valid",
    "outcome",
    "status",
    "reason",
}


def make_runtime_recovery_marker(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    return create_runtime_recovery_marker(
        runtime_checkpoint=make_runtime_checkpoint(decision_type, plan_type)
    )


def test_create_runtime_resume_marker_projects_independent_public_contract_only() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())

    assert marker == {
        "contract": RESUME_MARKER_CONTRACT,
        "outcome": "continue",
        "runtime_resume_marker": {
            "outcome": "continue",
            "source_outcome": "continue",
            "source_valid": True,
        },
        "valid": True,
        "errors": [],
    }
    assert set(marker) == EXPECTED_RESUME_KEYS
    assert set(marker["runtime_resume_marker"]) == EXPECTED_MARKER_KEYS
    assert "runtime_recovery_marker" not in marker
    assert "runtime_recovery_marker" not in marker["runtime_resume_marker"]
    assert "runtime_checkpoint" not in marker["runtime_resume_marker"]
    assert validate_runtime_resume_marker(marker)["valid"] is True


def test_resume_marker_preserves_valid_recovery_marker_outcomes() -> None:
    approval = create_runtime_resume_marker(
        runtime_recovery_marker=make_runtime_recovery_marker("continue", "request_approval")
    )
    stopped = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker("stop", "continue"))
    issue = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker("report_issue", "stop"))

    assert approval["outcome"] == "approval_required"
    assert stopped["outcome"] == "stopped"
    assert issue["outcome"] == "issue_reported"
    assert approval["valid"] is True
    assert stopped["valid"] is True
    assert issue["valid"] is True
    assert validate_runtime_resume_marker(issue)["valid"] is True


def test_resume_marker_does_not_forward_recovery_marker_wrapper_or_view_fields() -> None:
    recovery_marker = make_runtime_recovery_marker()
    recovery_marker["unknown_top_level"] = {"secret": "not forwarded"}
    recovery_marker["runtime_recovery_marker"]["unknown_marker"] = {"secret": "not forwarded"}

    marker = create_runtime_resume_marker(runtime_recovery_marker=recovery_marker)

    assert set(marker) == EXPECTED_RESUME_KEYS
    assert set(marker["runtime_resume_marker"]) == EXPECTED_MARKER_KEYS
    assert marker["valid"] is False
    assert marker["errors"] == ["invalid upstream contract"]
    assert "unknown_top_level" not in marker
    assert "runtime_recovery_marker" not in marker
    assert "unknown_marker" not in marker["runtime_resume_marker"]
    assert validate_runtime_resume_marker(marker)["valid"] is False


def test_resume_marker_projection_leak_seal_blocks_recovery_names_recursively() -> None:
    recovery_marker = make_runtime_recovery_marker()
    recovery_marker["recovery_marker_object"] = {"secret": "not forwarded"}
    recovery_marker["runtime_recovery_marker"]["recovery_marker_payload"] = {
        "secret": "not forwarded"
    }

    marker = create_runtime_resume_marker(runtime_recovery_marker=recovery_marker)
    encoded = json.dumps(marker, sort_keys=True)

    assert set(marker) == EXPECTED_RESUME_KEYS
    assert set(marker["runtime_resume_marker"]) == EXPECTED_MARKER_KEYS
    assert marker["runtime_resume_marker"] == {
        "outcome": "issue_reported",
        "source_outcome": "continue",
        "source_valid": False,
    }
    assert "runtime_recovery_marker" not in encoded
    assert "runtime_checkpoint" not in encoded
    assert "recovery_marker_object" not in encoded
    assert "recovery_marker_payload" not in encoded
    assert "recovery_marker_valid" not in encoded
    assert "checkpoint_valid" not in encoded


def test_resume_marker_internal_recovery_changes_only_affect_generic_source_fields() -> None:
    recovery_marker = make_runtime_recovery_marker()
    recovery_marker["runtime_recovery_marker"]["source_outcome"] = "stopped"

    marker = create_runtime_resume_marker(runtime_recovery_marker=recovery_marker)

    assert marker == {
        "contract": RESUME_MARKER_CONTRACT,
        "outcome": "issue_reported",
        "runtime_resume_marker": {
            "outcome": "issue_reported",
            "source_outcome": "continue",
            "source_valid": False,
        },
        "valid": False,
        "errors": ["invalid upstream contract"],
    }
    assert set(marker["runtime_resume_marker"]) == EXPECTED_MARKER_KEYS
    assert "runtime_recovery_marker" not in json.dumps(marker, sort_keys=True)


def test_runtime_resume_marker_to_summary_returns_fixed_public_summary_keys_only() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())
    marker["private"] = {"secret": "not exposed"}
    marker["runtime_resume_marker"]["private"] = {"secret": "not exposed"}
    marker["errors"] = ["not public"]

    summary = runtime_resume_marker_to_summary(marker)

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": False,
        "outcome": "continue",
        "status": "invalid",
        "reason": "invalid resume marker contract",
    }
    assert set(summary) == EXPECTED_SUMMARY_KEYS
    assert "private" not in summary
    assert "errors" not in summary
    assert "runtime_resume_marker" not in summary
    assert "runtime_recovery_marker" not in summary


def test_runtime_resume_marker_to_summary_projects_valid_marker_without_wrapper_leak() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())

    summary = runtime_resume_marker_to_summary(marker)
    encoded = json.dumps(summary, sort_keys=True)

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }
    assert set(summary) == EXPECTED_SUMMARY_KEYS
    assert "runtime_resume_marker" not in summary
    assert "source_outcome" not in summary
    assert "source_valid" not in summary
    assert "runtime_resume_marker" not in encoded
    assert "runtime_recovery_marker" not in encoded
    assert "runtime_checkpoint" not in encoded


def test_runtime_resume_marker_to_summary_is_independent_of_source_marker_mutation() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())

    summary = runtime_resume_marker_to_summary(marker)
    marker["outcome"] = "stopped"
    marker["valid"] = False
    marker["runtime_resume_marker"]["outcome"] = "stopped"
    marker["runtime_resume_marker"]["source_outcome"] = "stopped"
    marker["runtime_resume_marker"]["source_valid"] = False
    marker["errors"].append("invalid upstream contract")

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }


def test_invalid_runtime_resume_marker_summary_reports_generic_invalidity_only() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())
    marker["runtime_resume_marker"]["runtime_resume_marker"] = {
        "upstream_error": "runtime_recovery_marker leaked diagnostic"
    }
    marker["errors"] = ["runtime_recovery_marker leaked diagnostic"]

    summary = runtime_resume_marker_to_summary(marker)
    encoded = json.dumps(summary, sort_keys=True)

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": False,
        "outcome": "continue",
        "status": "invalid",
        "reason": "invalid resume marker contract",
    }
    assert set(summary) == EXPECTED_SUMMARY_KEYS
    assert "runtime_resume_marker" not in encoded
    assert "runtime_recovery_marker" not in encoded
    assert "upstream_error" not in encoded
    assert "leaked diagnostic" not in encoded


def test_invalid_runtime_resume_marker_summary_uses_default_outcome_when_unavailable() -> None:
    summary = runtime_resume_marker_to_summary(None)

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": False,
        "outcome": "continue",
        "status": "invalid",
        "reason": "invalid resume marker contract",
    }


def test_invalid_runtime_resume_marker_summary_preserves_readable_marker_outcome() -> None:
    marker = create_runtime_resume_marker(
        runtime_recovery_marker=make_runtime_recovery_marker("report_issue", "stop")
    )
    marker["runtime_resume_marker"]["source_valid"] = False
    marker["errors"] = ["internal diagnostic must not leak"]

    summary = runtime_resume_marker_to_summary(marker)
    encoded = json.dumps(summary, sort_keys=True)

    assert summary == {
        "contract": RESUME_MARKER_SUMMARY_CONTRACT,
        "valid": False,
        "outcome": "issue_reported",
        "status": "invalid",
        "reason": "invalid resume marker contract",
    }
    assert set(summary) == EXPECTED_SUMMARY_KEYS
    assert "runtime_resume_marker" not in encoded
    assert "internal diagnostic" not in encoded


def test_create_runtime_resume_marker_reports_non_dict_recovery_marker_as_invalid() -> None:
    marker = create_runtime_resume_marker(runtime_recovery_marker=None)

    assert marker["outcome"] == "issue_reported"
    assert marker["valid"] is False
    assert marker["errors"] == ["invalid upstream contract"]
    assert validate_runtime_resume_marker(marker)["valid"] is False


def test_valid_issue_reported_recovery_marker_remains_valid_resume_marker() -> None:
    recovery_marker = make_runtime_recovery_marker("report_issue", "stop")
    marker = create_runtime_resume_marker(runtime_recovery_marker=recovery_marker)

    assert validate_runtime_recovery_marker(recovery_marker)["valid"] is True
    assert marker["outcome"] == "issue_reported"
    assert marker["valid"] is True
    assert validate_runtime_resume_marker(marker)["valid"] is True


def test_validate_runtime_resume_marker_rejects_malformed_payloads() -> None:
    result = validate_runtime_resume_marker({})

    assert result["valid"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: runtime_resume_marker" in result["errors"]

    marker = create_runtime_resume_marker(runtime_recovery_marker=make_runtime_recovery_marker())
    marker["runtime_resume_marker"]["unexpected"] = "not allowed"

    result = validate_runtime_resume_marker(marker)

    assert result["valid"] is False
    assert "runtime_resume_marker fields must match declared contract" in result["errors"]


def test_resume_marker_field_purposes_are_documented_and_fixed() -> None:
    assert set(resume_module._FIELD_PURPOSES) == EXPECTED_RESUME_KEYS
    assert set(resume_module._MARKER_FIELD_PURPOSES) == EXPECTED_MARKER_KEYS


def test_runtime_resume_marker_exposes_only_public_api() -> None:
    assert resume_module.__all__ == [
        "create_runtime_resume_marker",
        "validate_runtime_resume_marker",
        "runtime_resume_marker_to_summary",
    ]


def test_runtime_resume_marker_uses_only_runtime_recovery_marker_contract_helpers() -> None:
    source = inspect.getsource(resume_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_runtime_recovery_marker" in source
    assert "runtime_recovery_marker_to_summary" in source
    assert all("runtime_checkpoint" not in line for line in import_lines)
    assert all("create_runtime_recovery_marker" not in line for line in import_lines)


def test_runtime_resume_marker_has_no_resume_or_runtime_behavior() -> None:
    source = inspect.getsource(resume_module)

    forbidden_tokens = (
        "open(",
        "pathlib",
        "os.",
        "save_",
        "load_",
        "write_",
        "persist",
        "store",
        "resume(",
        "recover(",
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
