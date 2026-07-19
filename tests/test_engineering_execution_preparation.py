from cli.zero_engineering_execution_preparation import build_pipeline
from tests.test_engineering_authorization_intake import authorization_pipeline


def authorization_closure():
    return authorization_pipeline()["closure"]


def preparation_pipeline(intent=None):
    return build_pipeline(authorization_closure(), intent or {})


def test_pipeline_closes_ready_without_granting_execution_or_mutation():
    artifacts = preparation_pipeline()
    assert artifacts["intake"]["status"] == "accepted"
    assert artifacts["validation"]["status"] == "validated"
    closure = artifacts["closure"]
    assert closure["status"] == "closed_ready"
    assert closure["preparation_decision"] == "ready_for_governed_execution"
    assert closure["boundary"]["approval_authority"] == "granted"
    assert closure["boundary"]["authorization_authority"] == "granted"
    assert closure["boundary"]["execution_authority"] == "not_granted"
    assert closure["boundary"]["mutation_authority"] == "not_granted"
    assert closure["governance_declaration"]["preparation_is_execution"] is False


def test_unmet_precondition_prevents_ready_closure():
    artifacts = preparation_pipeline({"preconditions": ["reviewed"], "met_preconditions": []})
    assert artifacts["preconditions"]["status"] == "not_satisfied"
    assert artifacts["validation"]["status"] == "invalid"
    assert artifacts["closure"]["status"] == "invalid"


def test_unavailable_environment_or_resource_prevents_ready_closure():
    environment = preparation_pipeline({"environment_requirements": ["isolated"], "available_environment_requirements": []})
    resources = preparation_pipeline({"resource_requirements": ["capacity"], "available_resources": []})
    assert environment["environment_requirements"]["status"] == "not_satisfied"
    assert resources["resource_plan"]["status"] == "not_satisfied"


def test_pipeline_is_deterministic():
    assert preparation_pipeline() == preparation_pipeline()
