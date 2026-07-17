from __future__ import annotations

from core.runtime.execution_authority import execution_authority_inventory
from core.runtime.runtime_execution_authority_policy import CANONICAL_EXECUTION_AUTHORITY_MATRIX
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]




def test_execution_authority_inventory_has_one_role_per_surface() -> None:
    inventory = execution_authority_inventory()
    surfaces = [entry["surface"] for entry in inventory]
    assert len(surfaces) == len(set(surfaces))
    assert {entry["role"] for entry in inventory} == {"ISSUER", "DELEGATE", "DISPATCH", "EXECUTE", "DESCRIBE"}


def test_only_canonical_endpoints_may_execute() -> None:
    executable = {entry["surface"] for entry in execution_authority_inventory() if entry["execute"]}
    assert executable == {
        "StepExecutor.execute_step",
        "execution_gateway.safe_subprocess_run",
        "Executor.execute_request",
    }
    assert all(entry["gate_required"] for entry in execution_authority_inventory() if entry["execute"])


def test_canonical_matrix_separates_issuers_delegates_and_endpoints() -> None:
    assert CANONICAL_EXECUTION_AUTHORITY_MATRIX["runtime_dispatcher"]["may_execute"] is False
    assert CANONICAL_EXECUTION_AUTHORITY_MATRIX["task_runner"]["requires_capability"] is True
    assert CANONICAL_EXECUTION_AUTHORITY_MATRIX["step_executor"]["may_execute"] is True
    assert CANONICAL_EXECUTION_AUTHORITY_MATRIX["execution_gateway"]["may_execute"] is True
