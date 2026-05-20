from __future__ import annotations

import pytest

from core.engineering.verification_evidence import (
    build_verification_evidence_bundle,
    validate_verification_evidence_contract,
)


def test_verification_evidence_bundle_records_passed_verification() -> None:
    bundle = build_verification_evidence_bundle(
        verification_route=_route(),
        exit_code=0,
        stdout="18 passed in 0.71s",
        stderr="",
    )
    payload = bundle.to_dict()

    assert payload["bundle_id"].startswith("verification-evidence-")
    assert payload["verification_route_id"] == "verification-route-123"
    assert payload["status"] == "passed"
    assert payload["failure_classification"] == "none"
    assert payload["retry_recommended"] is False
    assert payload["repair_eligible"] is False
    assert payload["metadata"]["verification_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_authority_granted"] is False
    assert payload["metadata"]["canonical_runtime_success"] is False
    assert validate_verification_evidence_contract(payload) is True


def test_verification_evidence_bundle_classifies_test_failure() -> None:
    bundle = build_verification_evidence_bundle(
        verification_route=_route(command="python -m pytest tests/test_alpha.py"),
        exit_code=1,
        stdout="FAILED tests/test_alpha.py::test_alpha",
        stderr="AssertionError",
    )
    payload = bundle.to_dict()

    assert payload["status"] == "failed"
    assert payload["failure_classification"] == "test_failure"
    assert payload["retry_recommended"] is True
    assert payload["repair_eligible"] is True


def test_verification_evidence_bundle_classifies_compile_failure() -> None:
    bundle = build_verification_evidence_bundle(
        verification_route=_route(command="python -m compileall core"),
        exit_code=1,
        stdout="",
        stderr="SyntaxError: invalid syntax",
    )
    payload = bundle.to_dict()

    assert payload["status"] == "failed"
    assert payload["failure_classification"] == "compile_failure"
    assert payload["retry_recommended"] is True
    assert payload["repair_eligible"] is True


def test_verification_evidence_bundle_classifies_timeout_without_repair_claim() -> None:
    bundle = build_verification_evidence_bundle(
        verification_route=_route(),
        exit_code=None,
        stdout="",
        stderr="",
        timed_out=True,
    )
    payload = bundle.to_dict()

    assert payload["status"] == "timeout"
    assert payload["failure_classification"] == "timeout"
    assert payload["retry_recommended"] is True
    assert payload["repair_eligible"] is False


def test_verification_evidence_rejects_routes_that_grant_authority() -> None:
    route = _route()
    route["metadata"]["execution_allowed"] = True

    with pytest.raises(ValueError, match="verification_route_must_not_grant_execution_authority"):
        build_verification_evidence_bundle(
            verification_route=route,
            exit_code=0,
            stdout="passed",
        )


def test_verification_evidence_contract_rejects_canonical_runtime_success_shape() -> None:
    payload = build_verification_evidence_bundle(
        verification_route=_route(),
        exit_code=0,
        stdout="passed",
    ).to_dict()

    assert validate_verification_evidence_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_verification_evidence_contract(payload) is False


def _route(command: str = "python -m pytest tests/test_alpha.py") -> dict[str, object]:
    return {
        "verification_route_id": "verification-route-123",
        "command": command,
        "metadata": {
            "verification_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "approval_required": True,
        },
    }
