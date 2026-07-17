from copy import deepcopy

from core.runtime.runtime_capability_bootstrap_plan import compute_plan_fingerprint, compute_step_fingerprint
from core.runtime.runtime_capability_bootstrap_plan_validation import validate_capability_bootstrap_plan
from tests.test_runtime_capability_bootstrap_plan import make_plan


def resign_step(step):
    step["fingerprint"] = compute_step_fingerprint(step); step["step_id"] = "bootstrap-step-" + step["fingerprint"][:24]


def test_valid_plan_and_identity_tamper():
    plan, _ = make_plan(); assert validate_capability_bootstrap_plan(plan).valid
    plan["fingerprint"] = "0" * 64
    assert "fingerprint_mismatch" in validate_capability_bootstrap_plan(plan).errors


def test_duplicate_missing_and_circular_dependencies_fail():
    original, _ = make_plan()
    duplicate = deepcopy(original); duplicate["ordered_steps"][1] = deepcopy(duplicate["ordered_steps"][0]); duplicate["ordered_steps"][1]["order"] = 1; resign_step(duplicate["ordered_steps"][1])
    duplicate["ordered_steps"][1]["step_id"] = duplicate["ordered_steps"][0]["step_id"]
    assert "duplicate_step" in validate_capability_bootstrap_plan(duplicate).errors
    missing = deepcopy(original); missing["ordered_steps"][0]["dependency_step_ids"] = ["missing"]; resign_step(missing["ordered_steps"][0])
    assert "missing_dependency" in validate_capability_bootstrap_plan(missing).errors
    circular = deepcopy(original); circular["ordered_steps"][0]["dependency_step_ids"] = [circular["ordered_steps"][1]["step_id"]]; resign_step(circular["ordered_steps"][0])
    circular["ordered_steps"][1]["dependency_step_ids"] = [circular["ordered_steps"][0]["step_id"]]; resign_step(circular["ordered_steps"][1])
    # Re-point the first edge after the second ID changes.
    circular["ordered_steps"][0]["dependency_step_ids"] = [circular["ordered_steps"][1]["step_id"]]; resign_step(circular["ordered_steps"][0])
    assert not validate_capability_bootstrap_plan(circular).valid


def test_sensitive_and_non_json_data_are_rejected():
    plan, _ = make_plan(); plan["planning_metadata"]["token"] = "secret"; plan["warnings"].append({"bad": object()})
    result = validate_capability_bootstrap_plan(plan)
    assert "sensitive_or_unsafe_value" in result.errors and "not_json_serializable" in result.errors
