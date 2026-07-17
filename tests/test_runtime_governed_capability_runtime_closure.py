from copy import deepcopy

from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime
from core.runtime.runtime_governed_capability_runtime_closure_validation import validate_governed_capability_runtime_closure
from core.runtime.runtime_governed_capability_runtime_validation import validate_governed_capability_runtime_state
from tests.test_runtime_governed_capability_runtime import completed_input


def test_runtime_closure_identity_and_claims(tmp_path):
    (tmp_path / "target.txt").touch()
    closure = run_governed_capability_runtime(completed_input(tmp_path))["runtime_orchestration_closure"]
    assert validate_governed_capability_runtime_closure(closure).valid
    assert closure["verification_status"] == "verified_closed"
    bad = deepcopy(closure); bad["mutation_performed_claim"] = True
    assert not validate_governed_capability_runtime_closure(bad).valid


def test_unknown_stage_status_is_rejected(tmp_path):
    (tmp_path / "target.txt").touch()
    result = run_governed_capability_runtime(completed_input(tmp_path))
    state = deepcopy(result["runtime_state"])
    state["stage_states"]["observation_closed"]["status"] = "unknown"
    assert not validate_governed_capability_runtime_state(state).valid
