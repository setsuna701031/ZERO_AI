from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint, SCHEMAS
from core.engineering.engineering_task_orchestration_validation import VERIFICATION_SCHEMA
from core.engineering.engineering_task_artifact_adapter import ArtifactAdapterDescriptor, EngineeringTaskArtifactAdapter
from core.engineering.repository_analysis_report import SCHEMA as ANALYSIS_SCHEMA, validate_repository_analysis_report
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_approval_decision import SCHEMA as APPROVAL_SCHEMA, validate_engineering_approval_decision
from core.engineering.engineering_authorization_decision import SCHEMA as AUTH_SCHEMA, validate_engineering_authorization_decision
from core.engineering.engineering_repair_candidate import SCHEMA as CANDIDATE_SCHEMA
from core.engineering.engineering_repair_candidate_validation import validate_engineering_repair_candidate
from core.engineering.engineering_repair_plan import SCHEMA as REPAIR_PLAN_SCHEMA
from core.engineering.engineering_repair_plan_validation import validate_engineering_repair_plan
from core.engineering.engineering_completion_foundation import (PROPOSAL_LINKAGE_SCHEMA, VERIFICATION_RESULT_SCHEMA, COMPLETION_SCHEMA, validate_proposal_linkage, validate_verification_result, validate_completion)
from core.engineering.engineering_verification_plan import SCHEMA as VERIFICATION_PLAN_SCHEMA
from core.engineering.engineering_verification_plan_validation import validate_verification_plan
from core.engineering.engineering_verification_admission import SCHEMA as VERIFICATION_ADMISSION_SCHEMA
from core.engineering.engineering_verification_admission_validation import validate_verification_admission
from core.engineering.engineering_verification_run import SCHEMA as VERIFICATION_RUN_SCHEMA
from core.engineering.engineering_verification_run_validation import validate_verification_run
from core.engineering.engineering_runtime_continuation import SCHEMA as RUNTIME_CONTINUATION_SCHEMA
from core.engineering.engineering_runtime_continuation_validation import validate_runtime_continuation
from core.engineering.engineering_failure_analysis import SCHEMA as FAILURE_ANALYSIS_SCHEMA
from core.engineering.engineering_failure_analysis_validation import validate_failure_analysis
from core.engineering.engineering_repair_continuation_eligibility import SCHEMA as REPAIR_CONTINUATION_ELIGIBILITY_SCHEMA
from core.engineering.engineering_repair_continuation_eligibility_validation import validate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_cycle import SCHEMA as REPAIR_CONTINUATION_CYCLE_SCHEMA
from core.engineering.engineering_repair_continuation_cycle_validation import validate_repair_continuation_cycle
from core.engineering.engineering_feedback_report import SCHEMA as FEEDBACK_REPORT_SCHEMA
from core.engineering.engineering_feedback_report_validation import validate_feedback_report
from core.engineering.engineering_execution_session import SESSION_SCHEMA, REPORT_SCHEMA, validate_engineering_execution_session
from core.engineering.engineering_execution_session_report import validate_execution_session_report
from core.engineering.engineering_bootstrap_request import SCHEMA as BOOTSTRAP_REQUEST_SCHEMA

class _R:
    def __init__(self, valid: bool, errors=()): self.valid=valid; self.errors=tuple(errors)

def _seal_valid(a: Mapping[str, Any], id_key: str, prefix: str, statuses: set[str]) -> _R:
    errors=[]
    if a.get('status') not in statuses: errors.append('status_invalid')
    ident=a.get(id_key); fp=a.get('fingerprint')
    if not ident or not str(ident).startswith(prefix+'-'): errors.append('id_invalid')
    body={k:v for k,v in a.items() if k!='fingerprint'}
    body_without_id={k:v for k,v in body.items() if k!=id_key}
    if fp not in (fingerprint(body), fingerprint(body_without_id)): errors.append('fingerprint_mismatch')
    return _R(not errors, errors)

def _proposal_validator(a):
    built=assemble_change_proposal(a)
    return _R(built.get('proposal_id')==a.get('proposal_id') and built.get('fingerprint')==a.get('fingerprint') and a.get('status')=='proposed', ('proposal_contract_mismatch',) if built.get('fingerprint')!=a.get('fingerprint') else ())

def _task_verification_validator(a):
    errors=[]
    if a.get('schema')!=VERIFICATION_SCHEMA: errors.append('schema_invalid')
    if a.get('status')!='passed': errors.append('status_invalid')
    if a.get('failed_count')!=0: errors.append('failed_count_nonzero')
    if not a.get('verification_id', '').startswith('engineering-task-verification-'): errors.append('id_invalid')
    if a.get('fingerprint') != fingerprint({k:v for k,v in a.items() if k!='fingerprint'}): errors.append('fingerprint_mismatch')
    return _R(not errors, errors)

def known_adapters() -> tuple[EngineeringTaskArtifactAdapter, ...]:
    from core.engineering.engineering_bootstrap_request_validation import validate_engineering_bootstrap_request
    from core.engineering.engineering_bootstrap_pipeline import RESULT_SCHEMA as BOOTSTRAP_RESULT_SCHEMA, validate_engineering_bootstrap_result
    def d(**kw): return ArtifactAdapterDescriptor(**kw)
    items = [
        (d(phase='bootstrap_request', supported_schema=BOOTSTRAP_REQUEST_SCHEMA, production_module='core.engineering.engineering_bootstrap_request_validation', validator_entry_point='validate_engineering_bootstrap_request', identity_field='bootstrap_request_id', status_field='bootstrap_status', accepted_statuses=('requested',), rejected_statuses=('invalid','blocked'), linkage_fields=('repository_identity',), validation_level='canonical_validator'),
         validate_engineering_bootstrap_request),
        (d(phase='bootstrap_result', supported_schema=BOOTSTRAP_RESULT_SCHEMA, production_module='core.engineering.engineering_bootstrap_pipeline', validator_entry_point='validate_engineering_bootstrap_result', identity_field='bootstrap_result_id', status_field='bootstrap_status', accepted_statuses=('proposal_ready',), rejected_statuses=('invalid','blocked','failed','insufficient_evidence'), linkage_fields=('repository_identity','bootstrap_request_identity'), validation_level='canonical_validator'),
         validate_engineering_bootstrap_result),
        (d(phase='analysis', supported_schema=ANALYSIS_SCHEMA, production_module='core.engineering.repository_analysis_report', validator_entry_point='validate_repository_analysis_report', identity_field='repository_analysis_report_id', accepted_statuses=('reported',), rejected_statuses=('partial','invalid'), linkage_fields=('repository_identity','task_identity')),
         validate_repository_analysis_report),
        (d(phase='candidate_selection', supported_schema=CANDIDATE_SCHEMA, production_module='core.engineering.engineering_repair_candidate_validation', validator_entry_point='validate_engineering_repair_candidate', identity_field='candidate_id', status_field='selection_status', accepted_statuses=('selected',), rejected_statuses=('invalid','blocked','not_selected'), linkage_fields=('repository_identity','task_id','analysis_identity'), validation_level='canonical_validator'),
         validate_engineering_repair_candidate),
        (d(phase='repair_plan', supported_schema=REPAIR_PLAN_SCHEMA, production_module='core.engineering.engineering_repair_plan_validation', validator_entry_point='validate_engineering_repair_plan', identity_field='repair_plan_id', status_field='plan_status', accepted_statuses=('planned',), rejected_statuses=('invalid','blocked'), linkage_fields=('repository_identity','task_id','analysis_identity','candidate_identity'), validation_level='canonical_validator'),
         validate_engineering_repair_plan),
        (d(phase='proposal', supported_schema='zero.engineering.change_proposal.v1', production_module='core.engineering.engineering_change_proposal', validator_entry_point='assemble_change_proposal', identity_field='proposal_id', accepted_statuses=('proposed',), rejected_statuses=('not_proposed',), linkage_fields=('repository_identity','task_identity')),
         _proposal_validator),
        (d(phase='proposal_linkage', supported_schema=PROPOSAL_LINKAGE_SCHEMA, production_module='core.engineering.engineering_completion_foundation', validator_entry_point='validate_proposal_linkage', identity_field='proposal_linkage_id', accepted_statuses=('linked',), rejected_statuses=('invalid',), linkage_fields=('repository_identity','task_id','analysis_identity','candidate_identity','repair_plan_identity','proposal_identity'), validation_level='canonical_validator'),
         lambda a: validate_proposal_linkage(a)),
        (d(phase='approval', supported_schema=APPROVAL_SCHEMA, production_module='core.engineering.engineering_approval_decision', validator_entry_point='validate_engineering_approval_decision', identity_field='approval_decision_id', status_field='decision', accepted_statuses=('approved',), rejected_statuses=('rejected','blocked','invalid','insufficient_evidence'), linkage_fields=('proposal_identity','task_identity')),
         validate_engineering_approval_decision),
        (d(phase='authorization', supported_schema=AUTH_SCHEMA, production_module='core.engineering.engineering_authorization_decision', validator_entry_point='validate_engineering_authorization_decision', identity_field='authorization_decision_id', status_field='decision', accepted_statuses=('authorized',), rejected_statuses=('denied','blocked','invalid','insufficient_evidence'), linkage_fields=('proposal_identity','approval_identity','task_identity')),
         validate_engineering_authorization_decision),
        (d(phase='authorized_scope', supported_schema=SCHEMAS['mutation_authorized_scope'], production_module='core.engineering.engineering_mutation_authorized_scope', validator_entry_point='seal_mutation_authorized_scope_result_contract', identity_field='authorized_scope_id', accepted_statuses=('sealed',), rejected_statuses=('empty','invalid'), linkage_fields=('authorization_identity',), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'authorized_scope_id','mutauth-scope',{'sealed'})),
        (d(phase='preparation', supported_schema='zero.engineering.mutation_preparation_closure.v1', production_module='core.engineering.engineering_mutation_preparation_closure', validator_entry_point='close_mutation_preparation_result_contract', identity_field='closure_id', accepted_statuses=('closed',), rejected_statuses=('not_closed',), linkage_fields=('approval_identity','scope_identity'), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'closure_id','mpc',{'closed'})),
        (d(phase='preparation_token', supported_schema='zero.engineering.mutation_preparation_token.v1', production_module='core.engineering.engineering_mutation_preparation_token', validator_entry_point='issue_mutation_preparation_token_result_contract', identity_field='token_id', accepted_statuses=('issued',), rejected_statuses=('not_issued',), linkage_fields=('preparation_identity','scope_identity'), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'token_id','mpt',{'issued'}) if a.get('token_consumed') is False and a.get('token_use_limit')==1 else _R(False,('token_not_single_use_available',))),
        (d(phase='authorization_token', supported_schema=SCHEMAS['mutation_authorization_token'], production_module='core.engineering.engineering_mutation_authorization_token', validator_entry_point='issue_mutation_authorization_token_result_contract', identity_field='token_id', accepted_statuses=('issued',), rejected_statuses=('not_issued','invalid'), linkage_fields=('authorization_identity','preparation_identity','transaction_identity'), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'token_id','mutauth-token',{'issued'}) if a.get('token_consumed') is False and a.get('use_limit')==1 else _R(False,('token_not_single_use_available',))),
        (d(phase='executor_handoff', supported_schema=SCHEMAS['mutation_executor_handoff'], production_module='core.engineering.engineering_mutation_executor_handoff', validator_entry_point='build_mutation_executor_handoff_result_contract', identity_field='handoff_id', accepted_statuses=('handed_off',), rejected_statuses=('not_handed_off',), linkage_fields=('authorization_identity','scope_identity','preparation_identity','token_identity','transaction_identity'), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'handoff_id','mutx-handoff',{'handed_off'})),
        (d(phase='execution_result', supported_schema='zero.engineering.workspace_mutation_result.v1', production_module='core.engineering.engineering_workspace_mutation_result', validator_entry_point='build_result_contract', identity_field='result_id', accepted_statuses=('succeeded','failed_rolled_back','failed_recovery_required','rejected','duplicate_suppressed'), rejected_statuses=('invalid',), linkage_fields=('transaction_identity',), validation_level='canonical_builder_result'),
         lambda a: _seal_valid(a,'result_id','wsmut-result',{'succeeded','failed_rolled_back','failed_recovery_required','rejected','duplicate_suppressed'})),
        (d(phase='verification_plan', supported_schema=VERIFICATION_PLAN_SCHEMA, production_module='core.engineering.engineering_verification_plan_validation', validator_entry_point='validate_verification_plan', identity_field='verification_plan_id', status_field='schema', accepted_statuses=(VERIFICATION_PLAN_SCHEMA,), rejected_statuses=('invalid',), linkage_fields=('task_id','repository_identity','execution_session_id','execution_result_identity'), validation_level='canonical_validator'),
         validate_verification_plan),
        (d(phase='verification_admission', supported_schema=VERIFICATION_ADMISSION_SCHEMA, production_module='core.engineering.engineering_verification_admission_validation', validator_entry_point='validate_verification_admission', identity_field='verification_admission_id', status_field='admission_status', accepted_statuses=('admitted',), rejected_statuses=('blocked','invalid','consumed'), linkage_fields=('verification_plan_identity','execution_session_id','execution_result_identity'), validation_level='canonical_validator'),
         validate_verification_admission),
        (d(phase='verification_run', supported_schema=VERIFICATION_RUN_SCHEMA, production_module='core.engineering.engineering_verification_run_validation', validator_entry_point='validate_verification_run', identity_field='verification_run_id', status_field='run_status', accepted_statuses=('passed',), rejected_statuses=('failed','blocked','invalid','runner_error'), linkage_fields=('verification_plan_identity','verification_admission_identity','execution_session_id','execution_result_identity'), validation_level='canonical_validator'),
         validate_verification_run),
        (d(phase='runtime_continuation', supported_schema=RUNTIME_CONTINUATION_SCHEMA, production_module='core.engineering.engineering_runtime_continuation_validation', validator_entry_point='validate_runtime_continuation', identity_field='runtime_continuation_id', status_field='decision', accepted_statuses=('continue_to_completion',), rejected_statuses=('remain_blocked','verification_failed','manual_intervention_required','invalid'), linkage_fields=('execution_session_id','execution_result_identity','verification_result_identity'), validation_level='canonical_validator'),
         validate_runtime_continuation),
        (d(phase='verification_result', supported_schema=VERIFICATION_RESULT_SCHEMA, production_module='core.engineering.engineering_completion_foundation', validator_entry_point='validate_verification_result', identity_field='verification_result_id', status_field='verification_status', accepted_statuses=('passed',), rejected_statuses=('failed','blocked','invalid','not_verified'), linkage_fields=('task_id','repository_identity','proposal_identity','repair_plan_identity','execution_identity'), validation_level='canonical_validator'),
         lambda a: validate_verification_result(a)),
        (d(phase='failure_analysis', supported_schema=FAILURE_ANALYSIS_SCHEMA, production_module='core.engineering.engineering_failure_analysis_validation', validator_entry_point='validate_failure_analysis', identity_field='failure_analysis_id', status_field='failure_classification', accepted_statuses=('test_assertion_failure','syntax_failure','static_policy_failure','missing_expected_file','unexpected_file_present','invalid_json','verification_timeout','verification_runner_error','execution_output_mismatch','insufficient_evidence','scope_conflict','unknown_failure'), rejected_statuses=('invalid',), linkage_fields=('task_id','repository_identity','execution_session_id','verification_result_identity','original_plan_identity'), validation_level='canonical_validator'),
         validate_failure_analysis),
        (d(phase='repair_continuation_eligibility', supported_schema=REPAIR_CONTINUATION_ELIGIBILITY_SCHEMA, production_module='core.engineering.engineering_repair_continuation_eligibility_validation', validator_entry_point='validate_repair_continuation_eligibility', identity_field='repair_continuation_eligibility_id', status_field='eligibility_status', accepted_statuses=('eligible',), rejected_statuses=('blocked','cycle_limit_reached','manual_intervention_required'), linkage_fields=('task_id','execution_session_id','failure_analysis_identity','verification_result_identity'), validation_level='canonical_validator'),
         validate_repair_continuation_eligibility),
        (d(phase='repair_continuation_cycle', supported_schema=REPAIR_CONTINUATION_CYCLE_SCHEMA, production_module='core.engineering.engineering_repair_continuation_cycle_validation', validator_entry_point='validate_repair_continuation_cycle', identity_field='repair_continuation_cycle_id', status_field='cycle_status', accepted_statuses=('analysis_ready','eligible','candidate_ready','plan_ready','proposal_ready','awaiting_human_approval'), rejected_statuses=('blocked','manual_intervention_required','invalid'), linkage_fields=('task_id','repository_identity','parent_execution_session_id','parent_verification_result_identity','failure_analysis_identity','eligibility_identity'), validation_level='canonical_validator'),
         validate_repair_continuation_cycle),
        (d(phase='feedback_report', supported_schema=FEEDBACK_REPORT_SCHEMA, production_module='core.engineering.engineering_feedback_report_validation', validator_entry_point='validate_feedback_report', identity_field='feedback_report_id', status_field='cycle_status', accepted_statuses=('awaiting_human_approval','eligible','proposal_ready'), rejected_statuses=('blocked','manual_intervention_required','invalid'), linkage_fields=('task_id','repository_identity','failed_verification_result_identity'), validation_level='canonical_validator'),
         validate_feedback_report),
        (d(phase='completion', supported_schema=COMPLETION_SCHEMA, production_module='core.engineering.engineering_completion_foundation', validator_entry_point='validate_completion', identity_field='completion_id', status_field='completion_status', accepted_statuses=('completed',), rejected_statuses=('not_completed','blocked','failed','invalid'), linkage_fields=('task_id','repository_identity','proposal_identity','verification_result_identity'), validation_level='canonical_validator'),
         lambda a: validate_completion(a)),
        (d(phase='execution_session', supported_schema=SESSION_SCHEMA, production_module='core.engineering.engineering_execution_session', validator_entry_point='validate_engineering_execution_session', identity_field='execution_session_id', status_field='session_status', accepted_statuses=('awaiting_approval','approved','authorized','prepared','ready_for_execution','awaiting_verification','verified','completed','closed'), rejected_statuses=('blocked','failed','invalid'), linkage_fields=('task_id','repository_identity','proposal_identity'), validation_level='canonical_validator'),
         validate_engineering_execution_session),
        (d(phase='execution_session_report', supported_schema=REPORT_SCHEMA, production_module='core.engineering.engineering_execution_session_report', validator_entry_point='validate_execution_session_report', identity_field='report_id', status_field='session_status', accepted_statuses=('awaiting_approval','approved','authorized','prepared','ready_for_execution','awaiting_verification','verified','completed','closed'), rejected_statuses=('blocked','failed','invalid'), linkage_fields=('execution_session_id','task_id','repository_identity'), validation_level='canonical_validator'),
         validate_execution_session_report),
        (d(phase='verification', supported_schema=VERIFICATION_SCHEMA, production_module='core.engineering.engineering_task_orchestration_validation', validator_entry_point='task_verification_validator', identity_field='verification_id', accepted_statuses=('passed',), rejected_statuses=('failed','invalid'), linkage_fields=('task_identity','transaction_identity'), validation_level='canonical_validator'),
         _task_verification_validator),
    ]
    return tuple(EngineeringTaskArtifactAdapter(desc, val) for desc, val in items)
