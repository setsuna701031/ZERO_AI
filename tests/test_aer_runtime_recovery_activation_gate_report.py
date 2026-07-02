from __future__ import annotations

import inspect

from core.runtime import aer_runtime_recovery_activation_gate as gate
from core.runtime import aer_runtime_recovery_activation_gate_report as gate_report


def _valid_invocation() -> dict[str, object]:
    return {
        "contract": gate.RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "endpoint_name": gate.RECOVERY_BINDING_ENDPOINT_NAME,
        "endpoint_declared": True,
        "endpoint_enabled": False,
        "endpoint_invokable": False,
        "endpoint_invoked": False,
        "invocation_allowed": False,
        "binding_disabled": True,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_gate() -> dict[str, object]:
    return gate.prepare_recovery_activation_gate(_valid_invocation(), gate_id="gate-1")


def test_public_surface_is_strict() -> None:
    assert gate_report.__all__ == [
        "RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT",
        "RECOVERY_ACTIVATION_GATE_DECISION_ALLOWED_STATUSES",
        "RECOVERY_ACTIVATION_GATE_DECISION_DENIED_CAPABILITIES",
        "prepare_recovery_activation_gate_report",
    ]


def test_activation_gate_report_prepares_disabled_state() -> None:
    report = gate_report.prepare_recovery_activation_gate_report(_valid_gate(), report_id="report-1")

    assert report["contract"] == gate_report.RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["activation_state"] == "disabled"
    assert report["gate_state"] == "closed"
    assert report["gate_open"] is False
    assert report["gate_enabled"] is False
    assert report["activation_granted"] is False
    assert report["activation_allowed"] is False
    assert report["recovery_enabled"] is False
    assert report["binding_disabled"] is True
    assert report["binding_applied"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_mainline_wiring_enabled"] is False
    assert report["endpoint_invoked"] is False
    assert report["event_emitted"] is False
    assert report["kill_switch_required"] is True
    assert report["admission_required"] is True
    assert report["single_entry_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_invalid_gate_blocks_report() -> None:
    report = gate_report.prepare_recovery_activation_gate_report({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["denied"] is False
    assert report["activation_gate_reference"] == {}
    assert "missing or incompatible" in str(report["reason"])


def test_activation_grant_request_is_denied() -> None:
    report = gate_report.prepare_recovery_activation_gate_report(_valid_gate(), request_activation_grant=True)
    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["activation_granted"] is False
    assert report["activation_state"] == "disabled"
    assert "prohibited" in str(report["reason"])


def test_report_source_avoids_runtime_imports() -> None:
    source = inspect.getsource(gate_report)
    forbidden_imports = [
        "import os",
        "import pathlib",
        "import subprocess",
        "import scheduler",
        "import task_runner",
        "import dispatcher",
        "import supervisor",
        "import native",
    ]
    for token in forbidden_imports:
        assert token not in source
