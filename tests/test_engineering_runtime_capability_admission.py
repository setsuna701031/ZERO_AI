from copy import deepcopy

from core.engineering.engineering_capability_registry import build_capability_registration, build_capability_registry
from core.engineering.engineering_runtime_capability_admission import build_runtime_capability_admission, validate_runtime_capability_admission
from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from core.engineering.engineering_runtime_request import build_engineering_runtime_request
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from tests.engineering_runtime_orchestrator_fixtures import request_payload

ADAPTER_ID = "zero.engineering.read-only-workspace"
ADAPTER_FP = "a" * 64


def registration(capability="repository.read", operation="repository.read", status="enabled", **changes):
    data = dict(capability_id=capability, capability_version="1", display_name=capability,
                owner_domain="engineering", owner_adapter_id=ADAPTER_ID, owner_adapter_fingerprint=ADAPTER_FP,
                supported_operations=[operation], read_only=True, mutation_capable=False,
                requires_operator_approval=False, requires_mutation_authorization=False,
                requires_adapter_activation=False, requires_activation_token=False,
                workspace_scope_type="repository_relative", allowed_execution_boundary="workspace_adapter",
                status=status, deprecation_replacement=None,
                registration_evidence=[{"kind":"explicit_fixture","reference":capability}])
    data.update(changes)
    return build_capability_registration(**data)


def inputs(registry=None, **changes):
    request = build_engineering_runtime_request(request_payload())
    session = build_engineering_runtime_session(request)
    data = dict(session=session, request=request, capability_registry=registry or build_capability_registry([registration()]),
                requested_capability_id="repository.read", requested_operation="repository.read",
                requested_adapter_id=ADAPTER_ID, requested_adapter_fingerprint=ADAPTER_FP)
    data.update(changes)
    return data


def admit(**changes): return build_runtime_capability_admission(**inputs(**changes))


def test_valid_registration_admitted_and_propagates_governance_and_linkage():
    result = admit()
    assert result["status"] == "admitted" and result["registered"] and result["eligible"]
    assert result["registry_fingerprint"] and result["registration_fingerprint"]
    assert set(result["governance_requirements"]) == {"read_only", "mutation_capable", "requires_operator_approval",
        "requires_mutation_authorization", "requires_adapter_activation", "requires_activation_token",
        "workspace_scope_type", "allowed_execution_boundary"}
    assert validate_runtime_capability_admission(result) == []


def test_missing_and_invalid_registry_block():
    assert admit(capability_registry=None)["status"] == "invalid_registry"
    value = build_capability_registry([registration()]); value["fingerprint"] = "bad"
    assert admit(capability_registry=value)["status"] == "invalid_registry"
    assert admit(requested_adapter_fingerprint="bad")["status"] == "invalid_request"


def test_absent_and_inactive_capabilities_block():
    assert admit(requested_capability_id="unknown")["status"] == "not_registered"
    for status in ("disabled", "blocked", "unavailable"):
        value = build_capability_registry([registration(status=status)])
        assert admit(registry=value)["status"] == "inactive"
    deprecated = build_capability_registry([registration(status="enabled"),
        registration("old.read", "old.read", status="deprecated", deprecation_replacement="repository.read")])
    assert admit(registry=deprecated, requested_capability_id="old.read", requested_operation="old.read")["status"] == "deprecated"


def test_operation_ambiguity_and_adapter_mismatches_block():
    assert admit(requested_operation="other.read")["status"] == "operation_unsupported"
    ambiguous = build_capability_registry([registration(operation="shared.read"), registration("workspace.observe", "shared.read")])
    assert admit(registry=ambiguous, requested_operation="shared.read")["status"] == "ambiguous"
    assert admit(requested_adapter_id="wrong.adapter")["status"] == "adapter_mismatch"
    assert admit(requested_adapter_fingerprint="b" * 64)["status"] == "adapter_mismatch"


def test_invalid_boundary_and_governance_declaration_are_invalid_registry():
    bad_boundary = build_capability_registry([registration(allowed_execution_boundary="unrestricted")])
    bad_governance = build_capability_registry([registration(read_only=False, mutation_capable=True,
        requires_mutation_authorization=False)])
    assert admit(registry=bad_boundary)["status"] == "invalid_registry"
    assert admit(registry=bad_governance)["status"] == "invalid_registry"


def test_failure_is_passive_and_stops_orchestration_before_downstream_work():
    payload = {"request": request_payload(), "capability_registry": build_capability_registry([registration(status="blocked")]),
               "requested_capability_id":"repository.read", "requested_operation":"repository.read",
               "requested_adapter_id":ADAPTER_ID, "requested_adapter_fingerprint":ADAPTER_FP}
    result = orchestrate_engineering_runtime(payload)
    admission = result["capability_admission"]
    assert result["admission"]["status"] == "not_admitted"
    assert result["result"]["status"] == "rejected"
    assert all(key not in result for key in ("analysis", "preparation", "execution"))
    assert all(admission[key] is False for key in ("adapter_selected", "adapter_invoked", "activation_performed",
        "token_consumed", "workspace_accessed", "mutation_performed", "approval_granted", "authorization_granted"))


def test_read_only_proceeds_but_mutation_does_not_bypass_gates():
    read = {"request": request_payload(), "capability_registry": build_capability_registry([registration()]),
            "requested_capability_id":"repository.read", "requested_operation":"repository.read",
            "requested_adapter_id":ADAPTER_ID, "requested_adapter_fingerprint":ADAPTER_FP}
    assert orchestrate_engineering_runtime(read)["analysis"]["status"] == "coordinated"
    mutation_registration = registration("workspace.mutate", "workspace.mutate", read_only=False, mutation_capable=True,
        requires_operator_approval=True, requires_mutation_authorization=True,
        owner_adapter_id="zero.engineering.mutation", allowed_execution_boundary="governed_mutation_executor")
    mutation = deepcopy(read); mutation.update(capability_registry=build_capability_registry([mutation_registration]),
        requested_capability_id="workspace.mutate", requested_operation="workspace.mutate",
        requested_adapter_id="zero.engineering.mutation")
    mutation["request"]["requested_orchestration_mode"] = "execute"; mutation["request"]["execution_requested"] = True
    result = orchestrate_engineering_runtime(mutation)
    assert result["capability_admission"]["status"] == "admitted"
    assert result.get("operator_pause", {}).get("status") != "satisfied"
    assert "authorization_pause" not in result and "execution" not in result


def test_resume_linkage_accepts_match_and_blocks_drift():
    first = admit()
    assert build_runtime_capability_admission(**inputs(prior_admission=first))["status"] == "admitted"
    changed_registry = build_capability_registry([registration(), registration("engineering.verify", "engineering.verify")])
    assert build_runtime_capability_admission(**inputs(registry=changed_registry, prior_admission=first))["status"] == "blocked"
    assert build_runtime_capability_admission(**inputs(requested_operation="other.read", prior_admission=first))["status"] == "blocked"
    changed_registration = build_capability_registry([registration(display_name="Changed")])
    assert build_runtime_capability_admission(**inputs(registry=changed_registration, prior_admission=first))["status"] == "blocked"
