from copy import deepcopy

from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_strategy_selector import select_capability_strategy
from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime
from core.runtime.runtime_governed_capability_runtime_closure_validation import validate_governed_capability_runtime_closure
from tests.test_runtime_capability_activation_verification_closure import closure as activation_closure
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
from tests.test_runtime_apply_execution_plan_builder import proposal, lineage

NOW = "2026-07-10T12:00:00+00:00"
LIMITS = {"max_file_bytes": 4096, "max_preview_bytes": 1024, "max_directory_entries": 32, "max_name_bytes": 255}


def runtime_input(root):
    profile = RuntimeCapabilityDetector([]).detect(detected_at="fixed").to_dict()
    strategy = select_capability_strategy(profile).to_dict()
    pp, approval, admission = lineage(proposal())
    explicit = {
        "workspace_root": str(root), "observation_kind": "existence", "relative_target": "target.txt",
        "observation_limits": deepcopy(LIMITS),
        "decision_question": {"question_id": "q-1", "question_type": "target_exists",
                              "target_reference": {"relative_target": "target.txt"},
                              "required_observation_kinds": ["existence"], "decision_scope": deepcopy(LIMITS)},
        "decision_proposal": {"proposal_id": "proposal-1", "proposal_type": "prepare_execution_plan_review",
                              "target_reference": {"relative_target": "target.txt"},
                              "proposed_outcome": "execution_plan_review_requested", "rationale_references": [{"artifact_id": "pending", "artifact_fingerprint": "pending"}],
                              "limitations_acknowledged": []},
        "requested_scope": deepcopy(LIMITS), "requested_effect_class": "future_execution_plan_review",
        "requested_permissions": {"filesystem_read": False, "filesystem_write": False, "filesystem_mutation": False,
                                  "external_process": False, "network": False, "model_invocation": False},
        "sufficiency_requirements": {"require_observed": True, "require_not_truncated": True,
                                     "require_target_type": True, "require_nonempty_evidence": True},
        "execution_intent": {"intent_id": "intent-1", "intent_type": "control_plane_preparation",
                             "target_descriptor": {"relative_target": "target.txt"}, "requested_operations": ["prepare", "validate"],
                             "expected_effects": [], "prohibited_effects": ["filesystem_mutation", "process_creation", "network_access", "model_invocation", "transaction_commit", "external_side_effect"],
                             "validation_requirements": [], "dry_run": True},
        "proposal": pp, "approval_record": approval, "admission_record": admission,
        "operator_review": {"review_id": "review-1", "operator_id": "operator-1", "decision": "approved", "reviewed_at": NOW, "expires_at": "2026-07-10T12:30:00+00:00"},
        "operator_execution_request": {"request_id": "operator-request-1", "requested_at": NOW, "expires_at": "2026-07-10T12:20:00+00:00"},
        "active_authorization_request": {"authorization_id": "active-auth-1", "decision": "authorized", "authorized_at": NOW, "expires_at": "2026-07-10T12:10:00+00:00",
                                         "acknowledged_risks": ["manual_active_boundary_required"], "acknowledged_no_automatic_commit": True, "acknowledged_manual_rollback_authority": True},
        "now": NOW,
    }
    return {"contract": "zero.runtime.governed_capability_runtime_input.v1", "schema_version": "1",
            "upstream_artifacts": {"resume_from": None, "capability_profile": profile, "capability_strategy": strategy,
                                   "activation_verification_closure": activation_closure(), "execution_authority": authority(),
                                   "execution_request": request(), "dry_run_bridge_closure": bridge_closure(),
                                   "observation_evidence_closure": None, "decision_readiness_closure": None,
                                   "decision_authorization_closure": None},
            "explicit_inputs": explicit,
            "runtime_options": {"stop_after_stage": None, "allow_read_only_observation": True,
                                "require_full_validation": True, "dry_run_only": True}}


def completed_input(root):
    value = runtime_input(root)
    first = run_governed_capability_runtime(value)
    readiness = first["canonical_artifact_bundle"]["decision_readiness_closure"]
    value["explicit_inputs"]["decision_proposal"]["rationale_references"] = [{
        "artifact_id": readiness["decision_readiness_closure_id"],
        "artifact_fingerprint": readiness["decision_readiness_closure_fingerprint"],
    }]
    value["explicit_inputs"]["decision_proposal"]["limitations_acknowledged"] = deepcopy(readiness["limitations"])
    return value


def test_complete_runtime_prepares_without_side_effects(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"unchanged")
    before = target.read_bytes()
    result = run_governed_capability_runtime(completed_input(tmp_path))
    assert target.read_bytes() == before
    assert result["runtime_state"]["runtime_status"] == "prepared"
    assert result["prepared_transaction_handoff"]["handoff_status"] == "prepared"
    assert result["transaction_integration_closure"]["verification_status"] == "verified_closed"
    assert validate_governed_capability_runtime_closure(result["runtime_orchestration_closure"]).valid
    assert result["audit_summary"]["transaction_execute_called"] is False
    assert all(v is False for v in result["runtime_state"]["permissions"].values())


def test_fail_closed_and_deterministic(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    assert run_governed_capability_runtime(value) == run_governed_capability_runtime(deepcopy(value))
    value["runtime_options"]["dry_run_only"] = False
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "blocked"
    assert result["prepared_transaction_handoff"] is None


def resumed_input(root, resume_from):
    value = completed_input(root)
    completed = run_governed_capability_runtime(value)
    bundle = completed["canonical_artifact_bundle"]
    upstream = value["upstream_artifacts"]
    upstream["resume_from"] = resume_from
    upstream["observation_evidence_closure"] = None
    upstream["decision_readiness_closure"] = None
    upstream["decision_authorization_closure"] = None
    if resume_from == "decision_readiness_closed":
        upstream["observation_evidence_closure"] = bundle["observation_evidence_closure"]
        upstream["decision_readiness_closure"] = bundle["decision_readiness_closure"]
    else:
        upstream["decision_authorization_closure"] = bundle["decision_authorization_closure"]
    return value


def test_three_resume_like_canonical_start_points(tmp_path):
    (tmp_path / "target.txt").touch()
    for resume in ("decision_readiness_closed", "decision_authorization_closed", "transaction_preparation_input_ready"):
        result = run_governed_capability_runtime(resumed_input(tmp_path, resume))
        assert result["runtime_state"]["runtime_status"] == "prepared", (resume, result["audit_summary"])
        assert result["runtime_orchestration_closure"]["verification_status"] == "verified_closed"
        assert result["runtime_state"]["stage_states"]["capability_ready"]["reasons"] == ["caller_provided_canonical_artifact"]


def test_resume_tampering_fails_closed(tmp_path):
    (tmp_path / "target.txt").touch()
    value = resumed_input(tmp_path, "decision_authorization_closed")
    value["upstream_artifacts"]["decision_authorization_closure"]["authorized_next_stage"] = "execute"
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "blocked"
    assert result["prepared_transaction_handoff"] is None
    value = resumed_input(tmp_path, "decision_readiness_closed")
    value["upstream_artifacts"]["decision_readiness_closure"]["authority_id"] = "replacement"
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "blocked"


def test_stop_after_stage_prevents_later_api(monkeypatch, tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    value["runtime_options"]["stop_after_stage"] = "observation_closed"
    monkeypatch.setattr("core.runtime.runtime_governed_capability_runtime.build_capability_decision_readiness_assessment",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("later API called")))
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "stopped"
    assert result["runtime_state"]["prepared_transaction_available"] is False
    assert result["runtime_orchestration_closure"]["verification_status"] != "verified_closed"
    assert result["runtime_state"]["stage_states"]["decision_readiness_closed"]["reasons"] == ["stop_after_stage_reached"]


def test_stop_after_authorization_prevents_transaction_preparation(monkeypatch, tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    value["runtime_options"]["stop_after_stage"] = "decision_authorization_closed"
    monkeypatch.setattr("core.runtime.runtime_governed_capability_runtime.prepare_capability_decision_transaction",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("transaction preparation called")))
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "stopped"
    assert result["prepared_transaction_handoff"] is None


def test_stop_after_capability_prevents_observation_api(monkeypatch, tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    value["runtime_options"]["stop_after_stage"] = "capability_ready"
    monkeypatch.setattr("core.runtime.runtime_governed_capability_runtime.build_capability_read_only_adapter_admission",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("observation API called")))
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "stopped"
    assert result["prepared_transaction_handoff"] is None


def test_stop_after_transaction_prepared_is_successful_terminal(tmp_path):
    (tmp_path / "target.txt").touch()
    value = completed_input(tmp_path)
    value["runtime_options"]["stop_after_stage"] = "transaction_prepared"
    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "prepared"
    assert result["runtime_state"]["prepared_transaction_available"] is True
    assert result["runtime_orchestration_closure"]["verification_status"] == "verified_closed"
