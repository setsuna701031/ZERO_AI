from core.engineering.engineering_capability_registry import *

ADAPTER_FP = "a" * 64


def registration(capability_id="repository.read", operation="repository.read", status="enabled", **changes):
    data = dict(capability_id=capability_id, capability_version="1", display_name=capability_id,
                owner_domain="engineering", owner_adapter_id="zero.engineering.read-only-workspace",
                owner_adapter_fingerprint=ADAPTER_FP, supported_operations=[operation], read_only=True,
                mutation_capable=False, requires_operator_approval=False,
                requires_mutation_authorization=False, requires_adapter_activation=False,
                requires_activation_token=False, workspace_scope_type="repository_relative",
                allowed_execution_boundary="workspace_adapter", status=status,
                deprecation_replacement=None, registration_evidence=[{"kind": "explicit_fixture", "reference": capability_id}])
    data.update(changes)
    return build_capability_registration(**data)


def registry(*items): return build_capability_registry(items or (registration(),))


def errors(item): return set(validate_capability_registration(item).errors)


def test_stable_identity_and_input_order_independence():
    a, b = registration(), registration("engineering.verify", "engineering.verify")
    assert registry(a, b) == registry(b, a)
    assert registry(a, b)["fingerprint"] == registry(a, b)["fingerprint"]


def test_registration_fingerprint_and_adapter_linkage_validation():
    item = registration(); item["display_name"] = "changed"
    assert "registration_identity_invalid" in errors(item)
    assert "adapter_linkage_invalid" in errors(registration(owner_adapter_fingerprint="bad"))


def test_duplicate_capability_rejected_and_operation_ambiguity_is_lookup_failure():
    duplicate = registry(registration(), registration(operation="other"))
    assert "duplicate_capability_id" in validate_capability_registry(duplicate).errors
    ambiguous = registry(registration("repository.read", "shared.read"), registration("workspace.observe", "shared.read"))
    result = lookup_operation(ambiguous, "shared.read")
    assert result["lookup_status"] == "ambiguous" and result["adapter_inferred"] is False


def test_governance_contradictions_are_rejected():
    assert "authority_mode_contradictory" in errors(registration(mutation_capable=True))
    assert "mutation_authorization_required" in errors(registration(read_only=False, mutation_capable=True))
    assert "activation_token_requires_activation" in errors(registration(requires_activation_token=True))


def test_boundaries_operations_and_deprecation_are_validated():
    assert "execution_boundary_invalid" in errors(registration(allowed_execution_boundary="unrestricted"))
    assert "supported_operations_invalid" in errors(registration(supported_operations=[]))
    assert "deprecation_linkage_invalid" in errors(registration(status="deprecated"))


def test_lookup_by_capability_and_operation():
    value = registry()
    assert lookup_capability(value, "repository.read")["lookup_status"] == "found"
    assert lookup_operation(value, "repository.read")["lookup_status"] == "found"
    assert lookup_capability(value, "unknown")["lookup_status"] == "unavailable"


def test_status_filtering_excludes_every_inactive_status_by_default():
    items = [registration("cap." + status, "op." + status, status=status,
                          deprecation_replacement="cap.enabled" if status == "deprecated" else None)
             for status in ("enabled", "disabled", "blocked", "unavailable", "deprecated")]
    value = registry(*items)
    assert [item["status"] for item in list_capabilities(value)["registrations"]] == ["enabled"]
    for status in ("disabled", "blocked", "unavailable", "deprecated"):
        assert lookup_capability(value, "cap." + status)["lookup_status"] == "unavailable"


def test_read_mutation_adapter_and_boundary_lists():
    mutation = registration("workspace.mutate", "workspace.mutate", read_only=False, mutation_capable=True,
                            requires_operator_approval=True, requires_mutation_authorization=True,
                            owner_adapter_id="zero.engineering.mutation", allowed_execution_boundary="governed_mutation_executor")
    value = registry(registration(), mutation)
    assert len(list_capabilities(value, read_only=True)["registrations"]) == 1
    assert len(list_capabilities(value, mutation_capable=True)["registrations"]) == 1
    assert len(list_capabilities(value, adapter_id="zero.engineering.mutation")["registrations"]) == 1
    assert len(list_capabilities(value, execution_boundary="workspace_adapter")["registrations"]) == 1


def test_registry_never_grants_or_executes_and_compatibility_seam_only_validates():
    value = registry(); result = validate_requested_capability(value, capability_id="repository.read",
        operation="repository.read", adapter_id="zero.engineering.read-only-workspace", adapter_fingerprint=ADAPTER_FP)
    assert result["lookup_status"] == "registered"
    assert all(result[key] is False for key in ("adapter_inferred", "adapter_invoked", "execution_performed",
                                                 "mutation_performed", "authority_granted", "operator_approval_granted",
                                                 "mutation_authorization_granted"))


def test_canonical_evidence_closure_and_no_absolute_path_leakage():
    value = registry()
    assert value["evidence"]["inventory_authoritative"] is False
    assert value["closure"] == {"status": "closed", "read_only": True, "adapter_invoked": False,
                                  "execution_performed": False, "mutation_performed": False, "authority_granted": False}
    bad = registration(registration_evidence=[{"source": "C:\\private\\source.py"}])
    assert "registration_evidence_invalid" in errors(bad)


def test_registry_identity_changes_with_authoritative_field():
    assert registry(registration())["fingerprint"] != registry(registration(display_name="Different"))["fingerprint"]
