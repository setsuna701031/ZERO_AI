from core.engineering.engineering_capability_registry import build_capability_registration, build_capability_registry
from core.engineering.engineering_runtime_capability_admission import build_runtime_capability_admission
from core.engineering.engineering_runtime_request import build_engineering_runtime_request
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from tests.engineering_runtime_orchestrator_fixtures import request_payload
from tests.runtime_adapter_activation_fixtures import pipeline as activation_pipeline

ADAPTER_ID = "zero.engineering.read-only-workspace"
ADAPTER_FP = "a" * 64
CAPABILITY_ID = "repository.read"
OPERATION = "repository.read"


def mainline_payload():
    raw_request = request_payload()
    request = build_engineering_runtime_request(raw_request)
    session = build_engineering_runtime_session(request)
    registration = build_capability_registration(
        capability_id=CAPABILITY_ID, capability_version="1", display_name=CAPABILITY_ID,
        owner_domain="engineering", owner_adapter_id=ADAPTER_ID, owner_adapter_fingerprint=ADAPTER_FP,
        supported_operations=[OPERATION], read_only=True, mutation_capable=False,
        requires_operator_approval=False, requires_mutation_authorization=False,
        requires_adapter_activation=False, requires_activation_token=False,
        workspace_scope_type="repository_relative", allowed_execution_boundary="workspace_adapter",
        status="enabled", deprecation_replacement=None,
        registration_evidence=[{"kind": "explicit_fixture", "reference": CAPABILITY_ID}],
    )
    registry = build_capability_registry([registration])
    capability = build_runtime_capability_admission(
        session=session, request=request, capability_registry=registry,
        requested_capability_id=CAPABILITY_ID, requested_operation=OPERATION,
        requested_adapter_id=ADAPTER_ID, requested_adapter_fingerprint=ADAPTER_FP,
    )
    activation = activation_pipeline(
        adapter_id=ADAPTER_ID, execution_session_id=session["session_id"],
        invocation_descriptor_id="descriptor-1", activation_scope=["scope.alpha"],
        authority_constraints={"valid": True, "consumed": False, "passive": True, "scope": ["scope.alpha"]},
    )["ho"]
    invocation = {
        "activation_handoff": activation, "request_fingerprint": request["fingerprint"],
        "workspace_id": request["workspace_id"], "capability_id": capability["capability_id"],
        "registry_id": capability["registry_id"], "registry_fingerprint": capability["registry_fingerprint"],
        "registration_id": capability["registration_id"], "registration_fingerprint": capability["registration_fingerprint"],
        "adapter_id": capability["owner_adapter_id"], "adapter_fingerprint": capability["owner_adapter_fingerprint"],
        "requested_invocation_scope": ["scope.alpha"],
        "requested_operation": {"operation_id": OPERATION, "declarative": True},
        "input_bindings": {"binding": "value"},
        "expected_output_contract": {"contract_id": "output.contract", "outputs": ["result"]},
        "invocation_constraints": {"passive_only": True}, "resource_constraints": {"cpu": 1, "memory": 128},
        "timeout_constraints": {"seconds": 30}, "environment_constraints": {"passive": True},
        "intake_context": {"context": "governance"},
    }
    return {"request": raw_request, "capability_registry": registry,
            "requested_capability_id": CAPABILITY_ID, "requested_operation": OPERATION,
            "requested_adapter_id": ADAPTER_ID, "requested_adapter_fingerprint": ADAPTER_FP,
            "adapter_invocation": invocation}
