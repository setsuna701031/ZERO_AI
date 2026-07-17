from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from core.runtime.runtime_capability_validation import validate_capability_profile
from core.runtime.runtime_capability_strategy_validation import validate_capability_strategy
from core.runtime.runtime_capability_activation_verification_closure_validation import validate_capability_activation_verification_closure
from core.runtime.runtime_capability_execution_authority_validation import validate_capability_execution_authority
from core.runtime.runtime_capability_bounded_execution_request_validation import validate_capability_bounded_execution_request
from core.runtime.runtime_capability_executor_bridge_verification_closure_validation import validate_capability_executor_bridge_verification_closure
from core.runtime.runtime_capability_read_only_adapter_admission import build_capability_read_only_adapter_admission
from core.runtime.runtime_capability_read_only_adapter_admission_validation import validate_capability_read_only_adapter_admission
from core.runtime.runtime_capability_bounded_observation_request import build_capability_bounded_observation_request
from core.runtime.runtime_capability_bounded_observation_request_validation import validate_capability_bounded_observation_request
from core.runtime.runtime_capability_safe_target_resolution import build_capability_safe_target_resolution
from core.runtime.runtime_capability_safe_target_resolution_validation import validate_capability_safe_target_resolution
from core.runtime.runtime_capability_read_only_observation_result import build_capability_read_only_observation_result
from core.runtime.runtime_capability_read_only_observation_result_validation import validate_capability_read_only_observation_result
from core.runtime.runtime_capability_observation_evidence_closure import close_capability_observation_evidence
from core.runtime.runtime_capability_observation_evidence_closure_validation import validate_capability_observation_evidence_closure
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance import build_capability_observation_evidence_consumer_acceptance
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance_validation import validate_capability_observation_evidence_consumer_acceptance
from core.runtime.runtime_capability_observation_evidence_relevance_assessment import build_capability_observation_evidence_relevance_assessment
from core.runtime.runtime_capability_observation_evidence_relevance_assessment_validation import validate_capability_observation_evidence_relevance_assessment
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment import build_capability_observation_evidence_sufficiency_assessment
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment_validation import validate_capability_observation_evidence_sufficiency_assessment
from core.runtime.runtime_capability_decision_readiness_assessment import build_capability_decision_readiness_assessment
from core.runtime.runtime_capability_decision_readiness_assessment_validation import validate_capability_decision_readiness_assessment
from core.runtime.runtime_capability_decision_readiness_closure import close_capability_decision_readiness
from core.runtime.runtime_capability_decision_readiness_closure_validation import validate_capability_decision_readiness_closure
from core.runtime.runtime_capability_bounded_decision_review_request import build_capability_bounded_decision_review_request
from core.runtime.runtime_capability_bounded_decision_review_request_validation import validate_capability_bounded_decision_review_request
from core.runtime.runtime_capability_decision_review_eligibility import build_capability_decision_review_eligibility
from core.runtime.runtime_capability_decision_review_eligibility_validation import validate_capability_decision_review_eligibility
from core.runtime.runtime_capability_decision_policy_evaluation import build_capability_decision_policy_evaluation
from core.runtime.runtime_capability_decision_policy_evaluation_validation import validate_capability_decision_policy_evaluation
from core.runtime.runtime_capability_decision_authorization import build_capability_decision_authorization
from core.runtime.runtime_capability_decision_authorization_validation import validate_capability_decision_authorization
from core.runtime.runtime_capability_decision_authorization_closure import close_capability_decision_authorization
from core.runtime.runtime_capability_decision_authorization_closure_validation import validate_capability_decision_authorization_closure
from core.runtime.runtime_capability_decision_transaction_preparation import prepare_capability_decision_transaction
from core.runtime.runtime_capability_prepared_transaction_handoff_validation import validate_capability_prepared_transaction_handoff
from core.runtime.runtime_capability_transaction_preparation_integration_closure_validation import validate_capability_transaction_preparation_integration_closure
from core.runtime.runtime_governed_capability_runtime_closure import close_governed_capability_runtime
from core.runtime.runtime_governed_capability_runtime_closure_validation import validate_governed_capability_runtime_closure
from core.runtime.runtime_governed_capability_runtime_validation import (
    CLAIMS, INPUT_CONTRACT, PERMISSIONS, RESULT_CONTRACT, SCHEMA_VERSION, STAGES,
    STATE_CONTRACT, detached_json_value, fingerprint,
    validate_governed_capability_runtime_input, validate_governed_capability_runtime_state,
)


def _valid(validator: Callable[[Any], Any], artifact: Any) -> bool:
    result = validator(artifact)
    return bool(getattr(result, "valid", False))


def _reference(value: Mapping[str, Any]) -> dict[str, str]:
    identity = next((k for k in value if k.endswith("_id")), "")
    digest = next((k for k in value if k.endswith("_fingerprint") or k == "fingerprint"), "")
    canonical_digest = str(value.get(digest, "")) if digest else fingerprint(value)
    return {"artifact_id": str(value.get(identity, "")), "artifact_fingerprint": canonical_digest}


class GovernedCapabilityRuntimeOrchestrator:
    """Fixed, fail-closed orchestration through zero-side-effect transaction preparation."""

    def run(self, runtime_input: Any) -> dict[str, Any]:
        validation = validate_governed_capability_runtime_input(runtime_input)
        if not validation.valid:
            return self._blocked(runtime_input, "capability_ready", list(validation.errors))
        source = detached_json_value(runtime_input)
        upstream, explicit, options = source["upstream_artifacts"], source["explicit_inputs"], source["runtime_options"]
        artifacts: dict[str, Any] = {}
        stage_results: dict[str, Any] = {}
        states = {name: {"status": "pending", "source": "orchestrator", "reasons": []} for name in STAGES}
        if upstream.get("resume_from") is not None:
            return self._run_resumed(source, artifacts, stage_results, states)

        supplied = (
            ("capability_ready", "capability_profile", validate_capability_profile),
            ("capability_ready", "capability_strategy", validate_capability_strategy),
            ("activation_ready", "activation_verification_closure", validate_capability_activation_verification_closure),
            ("execution_request_ready", "execution_authority", validate_capability_execution_authority),
            ("execution_request_ready", "execution_request", validate_capability_bounded_execution_request),
            ("dry_run_bridge_closed", "dry_run_bridge_closure", validate_capability_executor_bridge_verification_closure),
        )
        for stage, name, validator in supplied:
            artifact = upstream[name]
            if not _valid(validator, artifact):
                return self._blocked(source, stage, [f"{name}_validator_failure"], artifacts, stage_results, states)
            required_states = {
                "activation_verification_closure": ("status", "verified"),
                "execution_authority": ("status", "authorized"),
                "execution_request": ("status", "accepted"),
                "dry_run_bridge_closure": ("verification_status", "verified_closed"),
            }
            if name in required_states and artifact.get(required_states[name][0]) != required_states[name][1]:
                return self._blocked(source, stage, [f"{name}_not_ready"], artifacts, stage_results, states)
            artifacts[name] = deepcopy(artifact)
            states[stage] = {"status": "skipped", "source": "caller_canonical_artifact", "reasons": ["validated_upstream_artifact"]}
        stop = options.get("stop_after_stage")
        if stop in STAGES[:4]:
            return self._stopped(source, stop, artifacts, stage_results, states)
        authority = artifacts["execution_authority"]
        request = artifacts["execution_request"]
        bridge = artifacts["dry_run_bridge_closure"]
        if (request.get("authority_id") != authority.get("authority_id")
                or bridge.get("authority_id") != authority.get("authority_id")
                or bridge.get("request_id") != request.get("request_id")):
            return self._blocked(source, "dry_run_bridge_closed", ["lineage_mismatch"], artifacts, stage_results, states)

        states["observation_closed"] = {"status": "running", "source": "orchestrator", "reasons": []}
        admission = build_capability_read_only_adapter_admission(
            authority, request, bridge, workspace_root_descriptor=explicit["workspace_root"])
        observation_request = build_capability_bounded_observation_request(
            admission, request, observation_kind=explicit["observation_kind"],
            relative_target=explicit["relative_target"], limits=explicit["observation_limits"])
        resolution = build_capability_safe_target_resolution(admission, observation_request)
        observation_result = build_capability_read_only_observation_result(admission, observation_request, resolution)
        observation_closure = close_capability_observation_evidence(
            authority, request, bridge, admission, observation_request, resolution, observation_result)
        observation_items = (
            ("read_only_adapter_admission", admission, validate_capability_read_only_adapter_admission, "admission_status", "admitted"),
            ("bounded_observation_request", observation_request, validate_capability_bounded_observation_request, "request_status", "accepted"),
            ("safe_target_resolution", resolution, validate_capability_safe_target_resolution, "resolution_status", "resolved"),
            ("read_only_observation_result", observation_result, validate_capability_read_only_observation_result, "result_status", "observed"),
            ("observation_evidence_closure", observation_closure, validate_capability_observation_evidence_closure, "verification_status", "verified_closed"),
        )
        for name, artifact, validator, status_field, expected in observation_items:
            artifacts[name] = artifact
            if not _valid(validator, artifact) or artifact.get(status_field) != expected:
                return self._blocked(source, "observation_closed", [f"{name}_failed"], artifacts, stage_results, states)
        states["observation_closed"] = {"status": "completed", "source": "orchestrator", "reasons": ["observation_verified_closed"]}
        if stop == "observation_closed":
            return self._stopped(source, stop, artifacts, stage_results, states)

        acceptance = build_capability_observation_evidence_consumer_acceptance(observation_closure, observation_result)
        relevance = build_capability_observation_evidence_relevance_assessment(
            acceptance, observation_closure, observation_result, observation_request,
            decision_question=explicit["decision_question"])
        sufficiency = build_capability_observation_evidence_sufficiency_assessment(
            relevance, acceptance, observation_closure, observation_result,
            sufficiency_requirements=explicit["sufficiency_requirements"])
        readiness = build_capability_decision_readiness_assessment(acceptance, relevance, sufficiency, observation_closure)
        readiness_closure = close_capability_decision_readiness(
            authority, request, bridge, observation_closure, acceptance, relevance, sufficiency, readiness)
        readiness_items = (
            ("evidence_consumer_acceptance", acceptance, validate_capability_observation_evidence_consumer_acceptance, "acceptance_status", "accepted"),
            ("evidence_relevance", relevance, validate_capability_observation_evidence_relevance_assessment, "relevance_status", "relevant"),
            ("evidence_sufficiency", sufficiency, validate_capability_observation_evidence_sufficiency_assessment, "sufficiency_status", "sufficient"),
            ("decision_readiness", readiness, validate_capability_decision_readiness_assessment, "decision_status", "ready"),
            ("decision_readiness_closure", readiness_closure, validate_capability_decision_readiness_closure, "verification_status", "verified_closed"),
        )
        for name, artifact, validator, status_field, expected in readiness_items:
            artifacts[name] = artifact
            if not _valid(validator, artifact) or artifact.get(status_field) != expected:
                return self._blocked(source, "decision_readiness_closed", [f"{name}_failed"], artifacts, stage_results, states)
        states["decision_readiness_closed"] = {"status": "completed", "source": "orchestrator", "reasons": ["decision_ready"]}
        if stop == "decision_readiness_closed":
            return self._stopped(source, stop, artifacts, stage_results, states)

        review = build_capability_bounded_decision_review_request(
            readiness_closure, explicit["decision_proposal"], requested_scope=explicit["requested_scope"],
            requested_effect_class=explicit["requested_effect_class"], requested_permissions=explicit["requested_permissions"])
        eligibility = build_capability_decision_review_eligibility(review, readiness_closure)
        policy = build_capability_decision_policy_evaluation(eligibility, review, readiness_closure)
        authorization = build_capability_decision_authorization(policy, eligibility, review, readiness_closure)
        authorization_closure = close_capability_decision_authorization(
            authority, request, observation_closure, readiness_closure, review, eligibility, policy, authorization)
        authorization_items = (
            ("decision_review_request", review, validate_capability_bounded_decision_review_request),
            ("decision_review_eligibility", eligibility, validate_capability_decision_review_eligibility),
            ("decision_policy_evaluation", policy, validate_capability_decision_policy_evaluation),
            ("decision_authorization", authorization, validate_capability_decision_authorization),
            ("decision_authorization_closure", authorization_closure, validate_capability_decision_authorization_closure),
        )
        for name, artifact, validator in authorization_items:
            artifacts[name] = artifact
            if not _valid(validator, artifact):
                return self._blocked(source, "decision_authorization_closed", [f"{name}_validator_failure"], artifacts, stage_results, states)
        if authorization_closure.get("verification_status") != "verified_closed" or authorization_closure.get("authorized_next_stage") != "execution_plan_review_admission":
            return self._blocked(source, "decision_authorization_closed", ["decision_authorization_not_granted"], artifacts, stage_results, states)
        states["decision_authorization_closed"] = {"status": "completed", "source": "orchestrator", "reasons": ["decision_authorization_verified_closed"]}
        if stop == "decision_authorization_closed":
            return self._stopped(source, stop, artifacts, stage_results, states)

        transaction = prepare_capability_decision_transaction(
            authorization_closure, explicit["execution_intent"], proposal=explicit["proposal"],
            approval_record=explicit["approval_record"], admission_record=explicit["admission_record"],
            operator_review=explicit["operator_review"], operator_execution_request=explicit["operator_execution_request"],
            active_authorization_request=explicit["active_authorization_request"], target_root=explicit["workspace_root"], now=explicit["now"])
        artifacts.update({
            "execution_plan": transaction["execution_plan"], "execution_review": transaction["execution_review"],
            "executor_admission_token": transaction["admission_token"], "controlled_activation": transaction["controlled_activation"],
            "active_authorization": transaction["active_authorization"], "transaction_preparation": transaction["transaction_preparation"],
            "prepared_transaction_handoff": transaction["prepared_handoff"],
            "transaction_integration_closure": transaction["integration_closure"],
        })
        if transaction["active_authorization"].get("authorized_scope") != transaction["controlled_activation"].get("token", {}).get("allowed_files"):
            artifacts.pop("prepared_transaction_handoff", None)
            artifacts.pop("transaction_integration_closure", None)
            return self._blocked(source, "transaction_prepared", ["active_authorization_scope_expansion"], artifacts, stage_results, states)
        if (not _valid(validate_capability_prepared_transaction_handoff, transaction["prepared_handoff"])
                or not _valid(validate_capability_transaction_preparation_integration_closure, transaction["integration_closure"])
                or transaction["prepared_handoff"].get("handoff_status") != "prepared"
                or transaction["integration_closure"].get("verification_status") != "verified_closed"):
            return self._blocked(source, "transaction_prepared", ["transaction_preparation_not_prepared"], artifacts, stage_results, states)
        states["transaction_prepared"] = {"status": "completed", "source": "orchestrator", "reasons": ["prepared_transaction_handoff"]}
        return self._finish(source, artifacts, stage_results, states)

    def _run_resumed(self, source: Mapping[str, Any], artifacts: dict[str, Any],
                     stage_results: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
        upstream, explicit = source["upstream_artifacts"], source["explicit_inputs"]
        resume = upstream["resume_from"]
        authority, request = upstream.get("execution_authority"), upstream.get("execution_request")
        common = (("execution_authority", authority, validate_capability_execution_authority),
                  ("execution_request", request, validate_capability_bounded_execution_request))
        for name, artifact, validator in common:
            if not _valid(validator, artifact):
                return self._blocked(source, "execution_request_ready", [f"caller_provided_{name}_validator_failure"], artifacts, stage_results, states)
            artifacts[name] = deepcopy(artifact)
        if request.get("authority_id") != authority.get("authority_id"):
            return self._blocked(source, "execution_request_ready", ["caller_provided_lineage_mismatch"], artifacts, stage_results, states)

        authorization_closure: Mapping[str, Any]
        if resume == "decision_readiness_closed":
            observation = upstream.get("observation_evidence_closure")
            readiness = upstream.get("decision_readiness_closure")
            if not _valid(validate_capability_observation_evidence_closure, observation) or not _valid(validate_capability_decision_readiness_closure, readiness):
                return self._blocked(source, "decision_readiness_closed", ["caller_provided_canonical_artifact_validator_failure"], artifacts, stage_results, states)
            claims = ("execution_completion_claim", "authorization_claim", "decision_made_claim")
            lineage = (readiness.get("authority_id") == authority.get("authority_id")
                       and readiness.get("execution_request_id") == request.get("request_id")
                       and readiness.get("observation_closure_id") == observation.get("observation_closure_id"))
            question = readiness.get("decision_question", {})
            target_ok = question.get("target_reference") == {"relative_target": explicit["relative_target"]}
            scope_ok = question.get("decision_scope") == explicit["requested_scope"]
            if (readiness.get("verification_status") != "verified_closed" or readiness.get("closed") is not True
                    or any(readiness.get(k) is not False for k in claims) or not lineage or not target_ok or not scope_ok):
                return self._blocked(source, "decision_readiness_closed", ["caller_provided_readiness_invariant_failure"], artifacts, stage_results, states)
            artifacts.update({"observation_evidence_closure": deepcopy(observation), "decision_readiness_closure": deepcopy(readiness)})
            self._mark_resumed(states, "decision_readiness_closed", artifacts)
            if source["runtime_options"].get("stop_after_stage") == "decision_readiness_closed":
                return self._stopped(source, "decision_readiness_closed", artifacts, stage_results, states)
            review = build_capability_bounded_decision_review_request(
                readiness, explicit["decision_proposal"], requested_scope=explicit["requested_scope"],
                requested_effect_class=explicit["requested_effect_class"], requested_permissions=explicit["requested_permissions"])
            eligibility = build_capability_decision_review_eligibility(review, readiness)
            policy = build_capability_decision_policy_evaluation(eligibility, review, readiness)
            authorization = build_capability_decision_authorization(policy, eligibility, review, readiness)
            authorization_closure = close_capability_decision_authorization(
                authority, request, observation, readiness, review, eligibility, policy, authorization)
            for name, artifact, validator in (
                ("decision_review_request", review, validate_capability_bounded_decision_review_request),
                ("decision_review_eligibility", eligibility, validate_capability_decision_review_eligibility),
                ("decision_policy_evaluation", policy, validate_capability_decision_policy_evaluation),
                ("decision_authorization", authorization, validate_capability_decision_authorization),
                ("decision_authorization_closure", authorization_closure, validate_capability_decision_authorization_closure)):
                artifacts[name] = artifact
                if not _valid(validator, artifact):
                    return self._blocked(source, "decision_authorization_closed", [f"{name}_validator_failure"], artifacts, stage_results, states)
            states["decision_authorization_closed"] = {"status": "completed", "source": "orchestrator", "reasons": ["decision_authorization_verified_closed"]}
        else:
            authorization_closure = upstream.get("decision_authorization_closure")
            if not _valid(validate_capability_decision_authorization_closure, authorization_closure):
                return self._blocked(source, "decision_authorization_closed", ["caller_provided_canonical_artifact_validator_failure"], artifacts, stage_results, states)
            claims = ("execution_completion_claim", "mutation_authorization_claim", "external_execution_authorization_claim", "decision_executed_claim")
            target_ok = authorization_closure.get("target_reference") == explicit["execution_intent"].get("target_descriptor")
            scope_ok = authorization_closure.get("decision_question", {}).get("decision_scope") == explicit["requested_scope"]
            lineage = (authorization_closure.get("authority_id") == authority.get("authority_id")
                       and authorization_closure.get("execution_request_id") == request.get("request_id"))
            if (authorization_closure.get("verification_status") != "verified_closed"
                    or authorization_closure.get("closed") is not True
                    or authorization_closure.get("authorized_next_stage") != "execution_plan_review_admission"
                    or any(authorization_closure.get(k) is not False for k in claims)
                    or not target_ok or not scope_ok or not lineage):
                return self._blocked(source, "decision_authorization_closed", ["caller_provided_authorization_invariant_failure"], artifacts, stage_results, states)
            artifacts["decision_authorization_closure"] = deepcopy(authorization_closure)
            self._mark_resumed(states, "decision_authorization_closed", artifacts)
        if source["runtime_options"].get("stop_after_stage") == "decision_authorization_closed":
            return self._stopped(source, "decision_authorization_closed", artifacts, stage_results, states)
        return self._prepare_resumed_transaction(source, authorization_closure, artifacts, stage_results, states)

    @staticmethod
    def _mark_resumed(states: dict[str, Any], through: str, artifacts: Mapping[str, Any]) -> None:
        for name in STAGES[:STAGES.index(through) + 1]:
            states[name] = {"status": "skipped", "source": "caller_canonical_artifact",
                            "reasons": ["caller_provided_canonical_artifact"],
                            "validator_passed": True, "lineage_verified": True,
                            "canonical_artifact_references": sorted(artifacts)}

    def _prepare_resumed_transaction(self, source: Mapping[str, Any], authorization_closure: Mapping[str, Any],
                                     artifacts: dict[str, Any], stage_results: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
        explicit = source["explicit_inputs"]
        transaction = prepare_capability_decision_transaction(
            authorization_closure, explicit["execution_intent"], proposal=explicit["proposal"],
            approval_record=explicit["approval_record"], admission_record=explicit["admission_record"],
            operator_review=explicit["operator_review"], operator_execution_request=explicit["operator_execution_request"],
            active_authorization_request=explicit["active_authorization_request"], target_root=explicit["workspace_root"], now=explicit["now"])
        artifacts.update({"execution_plan": transaction["execution_plan"], "execution_review": transaction["execution_review"],
                          "executor_admission_token": transaction["admission_token"], "controlled_activation": transaction["controlled_activation"],
                          "active_authorization": transaction["active_authorization"], "transaction_preparation": transaction["transaction_preparation"],
                          "prepared_transaction_handoff": transaction["prepared_handoff"], "transaction_integration_closure": transaction["integration_closure"]})
        if transaction["active_authorization"].get("authorized_scope") != transaction["controlled_activation"].get("token", {}).get("allowed_files"):
            artifacts.pop("prepared_transaction_handoff", None)
            artifacts.pop("transaction_integration_closure", None)
            return self._blocked(source, "transaction_prepared", ["active_authorization_scope_expansion"], artifacts, stage_results, states)
        if (not _valid(validate_capability_prepared_transaction_handoff, transaction["prepared_handoff"])
                or not _valid(validate_capability_transaction_preparation_integration_closure, transaction["integration_closure"])
                or transaction["prepared_handoff"].get("handoff_status") != "prepared"
                or transaction["integration_closure"].get("verification_status") != "verified_closed"):
            return self._blocked(source, "transaction_prepared", ["transaction_preparation_not_prepared"], artifacts, stage_results, states)
        states["transaction_prepared"] = {"status": "completed", "source": "orchestrator", "reasons": ["prepared_transaction_handoff"]}
        return self._finish(source, artifacts, stage_results, states)

    def _state(self, source: Any, artifacts: Mapping[str, Any], states: Mapping[str, Any], status: str,
               reasons: list[str]) -> dict[str, Any]:
        safe_source = source if isinstance(source, Mapping) else {"invalid_input_type": type(source).__name__}
        try:
            input_fp = fingerprint(safe_source)
        except (TypeError, ValueError, OverflowError):
            safe_source = {"invalid_non_json_safe_input": True}
            input_fp = fingerprint(safe_source)
        explicit = safe_source.get("explicit_inputs", {}) if isinstance(safe_source, Mapping) else {}
        handoff = artifacts.get("prepared_transaction_handoff", {})
        references = {name: _reference(value) for name, value in artifacts.items() if isinstance(value, Mapping)}
        body = {
            "contract": STATE_CONTRACT, "schema_version": SCHEMA_VERSION,
            "input_id": "governed-capability-runtime-input-" + input_fp[:24], "input_fingerprint": input_fp,
            "current_stage": next((name for name in reversed(STAGES) if states.get(name, {}).get("status") != "pending"), STAGES[0]),
            "stage_order": list(STAGES), "stage_states": deepcopy(states), "artifact_references": references,
            "lineage_summary": {"artifact_count": len(references), "caller_supplied_stages": [n for n in STAGES if states.get(n, {}).get("source") == "caller_canonical_artifact"]},
            "target_boundary": deepcopy(handoff.get("target_boundary", {"relative_target": explicit.get("relative_target", "")})),
            "authorized_scope": deepcopy(handoff.get("authorized_scope", explicit.get("requested_scope", {}))),
            "effective_scope": deepcopy(handoff.get("authorized_scope", explicit.get("requested_scope", {}))),
            "limitations": deepcopy(handoff.get("limitations", [])), "dry_run_only": True,
            "permissions": {name: False for name in PERMISSIONS}, "runtime_status": status,
            "terminal": True, "prepared_transaction_available": status == "prepared",
            **{name: False for name in CLAIMS}, "reasons": reasons,
            "blocked_reasons": reasons if status == "blocked" else [], "failure_reasons": [],
        }
        value = fingerprint(body)
        return {**body, "runtime_id": "governed-capability-runtime-" + value[:24], "runtime_fingerprint": value}

    def _finish(self, source: Mapping[str, Any], artifacts: dict[str, Any], stage_results: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
        provisional = deepcopy(states)
        provisional["runtime_closed"] = {"status": "completed", "source": "orchestrator", "reasons": ["runtime_verified_closed"]}
        state = self._state(source, artifacts, provisional, "prepared", ["prepared_transaction_available"])
        closure = close_governed_capability_runtime(source, state, stage_results, artifacts)
        if not validate_governed_capability_runtime_state(state).valid or not validate_governed_capability_runtime_closure(closure).valid or closure.get("verification_status") != "verified_closed":
            return self._blocked(source, "runtime_closed", ["runtime_closure_validation_failed"], artifacts, stage_results, states)
        return {
            "contract": RESULT_CONTRACT, "schema_version": SCHEMA_VERSION, "runtime_state": state,
            "stage_results": detached_json_value(stage_results), "canonical_artifact_bundle": detached_json_value(artifacts),
            "prepared_transaction_handoff": deepcopy(artifacts["prepared_transaction_handoff"]),
            "transaction_integration_closure": deepcopy(artifacts["transaction_integration_closure"]),
            "runtime_orchestration_closure": closure,
            "audit_summary": {"status": "prepared", "side_effects_performed": [], "transaction_execute_called": False,
                              "permissions": {name: False for name in PERMISSIONS}, "claims": {name: False for name in CLAIMS}},
        }

    def _stopped(self, source: Mapping[str, Any], stage: str, artifacts: dict[str, Any],
                 stage_results: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
        reached = STAGES.index(stage)
        for name in STAGES[reached + 1:]:
            states[name] = {"status": "skipped", "source": "stop_after_stage",
                            "reasons": ["stop_after_stage_reached"]}
        state = self._state(source, artifacts, states, "stopped", ["stop_after_stage_reached"])
        closure = close_governed_capability_runtime(source, state, stage_results, artifacts)
        return {
            "contract": RESULT_CONTRACT, "schema_version": SCHEMA_VERSION, "runtime_state": state,
            "stage_results": detached_json_value(stage_results), "canonical_artifact_bundle": detached_json_value(artifacts),
            "prepared_transaction_handoff": (deepcopy(artifacts.get("prepared_transaction_handoff"))
                                                 if artifacts.get("prepared_transaction_handoff", {}).get("handoff_status") == "prepared"
                                                 and _valid(validate_capability_prepared_transaction_handoff,
                                                            artifacts.get("prepared_transaction_handoff")) else None),
            "transaction_integration_closure": deepcopy(artifacts.get("transaction_integration_closure")),
            "runtime_orchestration_closure": closure,
            "audit_summary": {"status": "stopped", "side_effects_performed": [], "transaction_execute_called": False,
                              "permissions": {name: False for name in PERMISSIONS}, "claims": {name: False for name in CLAIMS},
                              "reasons": ["stop_after_stage_reached"]},
        }

    def _blocked(self, source: Any, stage: str, reasons: list[str], artifacts: dict[str, Any] | None = None,
                 stage_results: dict[str, Any] | None = None, states: dict[str, Any] | None = None) -> dict[str, Any]:
        artifacts = artifacts or {}
        stage_results = stage_results or {}
        states = states or {name: {"status": "pending", "source": "orchestrator", "reasons": []} for name in STAGES}
        states[stage] = {"status": "blocked", "source": states.get(stage, {}).get("source", "orchestrator"), "reasons": reasons}
        reached = False
        for name in STAGES:
            if name == stage:
                reached = True
            elif reached and states[name]["status"] == "pending":
                states[name] = {"status": "skipped", "source": "fail_closed", "reasons": ["prior_stage_blocked"]}
        state = self._state(source, artifacts, states, "blocked", reasons)
        closure = close_governed_capability_runtime(source if isinstance(source, Mapping) else {}, state, stage_results, artifacts)
        return {
            "contract": RESULT_CONTRACT, "schema_version": SCHEMA_VERSION, "runtime_state": state,
            "stage_results": detached_json_value(stage_results), "canonical_artifact_bundle": detached_json_value(artifacts),
            "prepared_transaction_handoff": (deepcopy(artifacts.get("prepared_transaction_handoff"))
                                                 if artifacts.get("prepared_transaction_handoff", {}).get("handoff_status") == "prepared"
                                                 and _valid(validate_capability_prepared_transaction_handoff,
                                                            artifacts.get("prepared_transaction_handoff")) else None),
            "transaction_integration_closure": deepcopy(artifacts.get("transaction_integration_closure")),
            "runtime_orchestration_closure": closure,
            "audit_summary": {"status": "blocked", "side_effects_performed": [], "transaction_execute_called": False,
                              "permissions": {name: False for name in PERMISSIONS}, "claims": {name: False for name in CLAIMS}, "reasons": reasons},
        }


def run_governed_capability_runtime(runtime_input: Any) -> dict[str, Any]:
    return GovernedCapabilityRuntimeOrchestrator().run(runtime_input)
