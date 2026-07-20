from copy import deepcopy

import pytest

from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
import core.engineering.engineering_runtime_orchestrator as orchestrator_module
from core.engineering.engineering_runtime_adapter_invocation_intake import validate_runtime_adapter_invocation_intake_request, validate_runtime_adapter_invocation_intake
from core.engineering.engineering_runtime_adapter_invocation_admission import validate_runtime_adapter_invocation_admission
from core.engineering.engineering_runtime_adapter_invocation_preparation import validate_runtime_adapter_invocation_preparation
from core.engineering.engineering_runtime_adapter_invocation_review import validate_runtime_adapter_invocation_review
from core.engineering.engineering_runtime_adapter_invocation_authorization import validate_runtime_adapter_invocation_authorization
from core.engineering.engineering_runtime_adapter_controlled_invocation import validate_runtime_adapter_controlled_invocation
from core.engineering.engineering_runtime_adapter_invocation_result import validate_runtime_adapter_invocation_result
from core.engineering.engineering_runtime_adapter_invocation_verification import validate_runtime_adapter_invocation_verification
from core.engineering.engineering_runtime_adapter_invocation_evidence import validate_runtime_adapter_invocation_evidence
from core.engineering.engineering_runtime_adapter_invocation_handoff import validate_runtime_adapter_invocation_handoff
from core.engineering.engineering_runtime_adapter_invocation_closure import validate_runtime_adapter_invocation_governance_closure
from tests.engineering_runtime_adapter_invocation_mainline_fixtures import mainline_payload


def test_complete_mainline_chain_is_sealed_valid_and_passive():
    first = orchestrate_engineering_runtime(mainline_payload())
    second = orchestrate_engineering_runtime(deepcopy(mainline_payload()))
    assert first == second
    assert first["result"]["status"] == "completed_without_mutation"
    validators = {
        "invocation_request": validate_runtime_adapter_invocation_intake_request,
        "invocation_intake": validate_runtime_adapter_invocation_intake,
        "invocation_admission": validate_runtime_adapter_invocation_admission,
        "invocation_preparation": validate_runtime_adapter_invocation_preparation,
        "invocation_review": validate_runtime_adapter_invocation_review,
        "invocation_authorization": validate_runtime_adapter_invocation_authorization,
        "controlled_invocation": validate_runtime_adapter_controlled_invocation,
        "invocation_result": validate_runtime_adapter_invocation_result,
        "invocation_verification": validate_runtime_adapter_invocation_verification,
        "invocation_evidence": validate_runtime_adapter_invocation_evidence,
        "passive_invocation_handoff": validate_runtime_adapter_invocation_handoff,
        "invocation_closure": validate_runtime_adapter_invocation_governance_closure,
    }
    assert all(validator(first[name]).valid for name, validator in validators.items())
    references = first["result"]["component_references"]
    assert references["invocation_result"]["fingerprint"] == first["invocation_result"]["fingerprint"]
    assert references["invocation_verification"]["fingerprint"] == first["invocation_verification"]["fingerprint"]
    assert references["invocation_evidence"]["fingerprint"] == first["invocation_evidence"]["fingerprint"]
    assert references["invocation_closure"]["fingerprint"] == first["invocation_closure"]["fingerprint"]
    assert all(first["invocation_result"][key] is False for key in ("adapter_invoked", "executor_invoked", "mutation_performed"))


@pytest.mark.parametrize(("path", "value", "reason"), [
    (("activation_handoff", "execution_session_id"), "foreign-session", "session_linkage_mismatch"),
    (("request_fingerprint",), "b" * 64, "request_linkage_mismatch"),
    (("workspace_id",), "foreign-workspace", "workspace_identity_mismatch"),
    (("capability_id",), "other.capability", "capability_linkage_mismatch"),
    (("requested_operation", "operation_id"), "other.operation", "operation_linkage_mismatch"),
    (("adapter_id",), "other.adapter", "adapter_linkage_mismatch"),
    (("adapter_fingerprint",), "b" * 64, "adapter_fingerprint_mismatch"),
    (("registry_fingerprint",), "b" * 64, "registry_fingerprint_mismatch"),
    (("registry_id",), "other-registry", "registry_linkage_mismatch"),
    (("registration_fingerprint",), "b" * 64, "registration_fingerprint_mismatch"),
    (("registration_id",), "other-registration", "registration_linkage_mismatch"),
    (("activation_handoff", "fingerprint"), "b" * 64, "activation_handoff_invalid"),
    (("activation_handoff", "adapter_id"), "other.adapter", "activation_handoff_invalid"),
])
def test_linkage_mismatch_fails_closed(path, value, reason):
    payload = mainline_payload(); target = payload["adapter_invocation"]
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    result = orchestrate_engineering_runtime(payload)
    assert result["result"]["status"] == "invalid"
    assert reason in result["result"]["reason_codes"]
    assert result["phase"]["phase"] == "request_received"
    assert all(key not in result for key in ("analysis", "execution"))


@pytest.mark.parametrize("field", ["activation_handoff", "invocation_constraints", "environment_constraints",
                                    "resource_constraints", "input_bindings", "timeout_constraints", "intake_context",
                                    "requested_invocation_scope", "expected_output_contract"])
def test_required_invocation_input_is_not_inferred(field):
    payload = mainline_payload(); payload["adapter_invocation"].pop(field)
    result = orchestrate_engineering_runtime(payload)
    assert result["result"]["status"] == "invalid"
    assert "missing_" + field in result["result"]["reason_codes"]


def test_capability_admission_is_required_and_linked():
    payload = mainline_payload()
    for key in ("capability_registry", "requested_capability_id", "requested_operation", "requested_adapter_id", "requested_adapter_fingerprint"):
        payload.pop(key)
    result = orchestrate_engineering_runtime(payload)
    assert result["result"]["status"] == "invalid"
    assert "capability_not_admitted" in result["result"]["reason_codes"]


def test_non_admitted_capability_blocks_invocation():
    payload = mainline_payload(); payload["requested_adapter_fingerprint"] = "b" * 64
    result = orchestrate_engineering_runtime(payload)
    assert result["capability_admission"]["status"] == "adapter_mismatch"
    assert result["result"]["status"] == "invalid"
    assert "capability_not_admitted" in result["result"]["reason_codes"]
    assert all(key not in result for key in ("invocation_result", "analysis", "execution"))


def test_invocation_result_fingerprint_tampering_is_rejected():
    result = orchestrate_engineering_runtime(mainline_payload())["invocation_result"]
    result["fingerprint"] = "b" * 64
    assert not validate_runtime_adapter_invocation_result(result).valid


def test_not_closed_is_invalid_and_never_previewed(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "orchestrate_runtime_adapter_invocation",
                        lambda *args: {"status": "not_closed", "reason_codes": ["not_closed"], "artifacts": {}})
    result = orchestrate_engineering_runtime(mainline_payload())
    assert result["result"]["status"] == "invalid"
    assert result["result"]["reason_codes"] == ["not_closed"]
    assert result["phase"]["phase"] == "request_received"


def test_legacy_preview_and_failure_mapping_are_unchanged():
    preview = orchestrate_engineering_runtime({"request_id": "r", "workspace_id": "w", "workspace_root_fingerprint": "f"})
    assert preview["result"]["status"] == "previewed"
    payload = mainline_payload(); payload.pop("adapter_invocation"); payload["capability_registry"]["fingerprint"] = "bad"
    failed = orchestrate_engineering_runtime(payload)
    assert failed["result"]["status"] == "rejected"
