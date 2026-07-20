from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_transaction_common import finish as tx_finish, fingerprint
from core.engineering.engineering_mutation_preparation_common import artifact as prep_artifact, SCHEMAS as PREP_SCHEMAS
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_approval_decision import build_engineering_approval_decision
from core.engineering.engineering_authorization_decision import build_engineering_authorization_decision
from core.engineering.engineering_task_orchestration_validation import VERIFICATION_SCHEMA
from core.engineering.repository_analysis_report import build_repository_analysis_report


def structural(schema: str, id_key: str, prefix: str, status: str, **extra: Any) -> dict[str, Any]:
    body = {"schema": schema, "status": status, **extra}
    fp = fingerprint(body)
    body[id_key] = prefix + "-" + fp[:24]
    body["fingerprint"] = fingerprint({k: v for k, v in body.items() if k != "fingerprint"})
    return body


def analysis_report() -> dict[str, Any]:
    def a(schema, status, id_key, prefix):
        return structural(schema, id_key, prefix, status)
    req=a('zero.engineering.repository_analysis_request.v1','prepared','repository_analysis_request_id','engineering-repository-analysis-request')
    admission=a('zero.engineering.repository_root_admission.v1','admitted','repository_root_admission_id','engineering-root-admission')
    snapshot={**a('zero.engineering.repository_snapshot.v1','captured','repository_snapshot_id','engineering-repository-snapshot'), 'entries':[], 'truncated':False}
    topology={**a('zero.engineering.repository_topology.v1','mapped','repository_topology_id','engineering-repository-topology'), 'top_level_directories':[], 'package_roots':[]}
    lang={**a('zero.engineering.repository_language_discovery.v1','discovered','repository_language_discovery_id','engineering-repository-language'), 'languages':[], 'primary_language_candidates':[]}
    build={**a('zero.engineering.repository_build_discovery.v1','discovered','repository_build_discovery_id','engineering-repository-build'), 'detected_build_systems':[], 'manifest_paths':[]}
    test={**a('zero.engineering.repository_test_discovery.v1','discovered','repository_test_discovery_id','engineering-repository-test'), 'test_file_count':0, 'framework_evidence':[]}
    dep={**a('zero.engineering.repository_dependency_analysis.v1','analyzed','repository_dependency_analysis_id','engineering-repository-dependency'), 'python_import_edges':[]}
    inv={**a('zero.engineering.repository_engineering_inventory.v1','inventoried','repository_engineering_inventory_id','engineering-inventory'), 'core_modules':[], 'runtime_modules':[], 'engineering_modules':[], 'cli_modules':[], 'test_modules':[]}
    evidence={**a('zero.engineering.repository_analysis_evidence.v1','recorded','repository_analysis_evidence_id','engineering-repository-evidence'), 'evidence_items':[]}
    return build_repository_analysis_report(req, admission, snapshot, topology, lang, build, test, dep, inv, evidence)


def candidate_selection() -> dict[str, Any]:
    return structural('zero.engineering.task_candidate_selection.v1','candidate_selection_id','engineering-task-candidate-selection','selected')


def repair_plan() -> dict[str, Any]:
    return structural('zero.engineering.task_repair_plan.v1','repair_plan_id','engineering-task-repair-plan','planned')


def proposal() -> dict[str, Any]:
    return assemble_change_proposal({'intent': {'intent_id': 'intent-1'}, 'workspace_evidence': {'workspace_id': 'ws-task'}, 'scope_policy': {'maximum_affected_files': 1, 'maximum_total_proposed_content_bytes': 32}, 'operations': [], 'contents': []})


def approval_decision() -> dict[str, Any]:
    intake={'status':'accepted','approval_intake_id':'intake-1','requested_decision':'approve'}
    eligibility={'status':'eligible','approval_eligibility_id':'elig-1','blocking_conditions':[]}
    policy={'status':'satisfied','approval_policy_id':'policy-1','policy_findings':[]}
    return build_engineering_approval_decision(intake, eligibility, policy)


def authorization_decision() -> dict[str, Any]:
    intake={'status':'accepted','authorization_intake_id':'auth-intake-1','requested_decision':'authorize'}
    eligibility={'status':'eligible','authorization_eligibility_id':'auth-elig-1','blocking_conditions':[]}
    policy={'status':'satisfied','authorization_policy_id':'auth-policy-1','policy_findings':[]}
    return build_engineering_authorization_decision(intake, eligibility, policy)


def preparation_closure() -> dict[str, Any]:
    return prep_artifact('mpc', PREP_SCHEMAS['mutation_preparation_closure'], {'status':'closed','token_consumed':False}, 'closure_id')


def authorization_token(transaction_id: str = 'tx-1') -> dict[str, Any]:
    return tx_finish('mutauth-token','mutation_authorization_token','token_id', {'status':'issued','use_limit':1,'token_consumed':False,'token_purpose':'workspace_mutation_transaction_admission','transaction_id':transaction_id})


def executor_handoff() -> dict[str, Any]:
    return tx_finish('mutx-handoff','mutation_executor_handoff','handoff_id', {'status':'handed_off'})


def execution_result() -> dict[str, Any]:
    from core.engineering.engineering_workspace_mutation_executor_common import finish
    return finish('wsmut-result','result','result_id', {'status':'succeeded'})


def task_verification(task_id: str, transaction_identity: Any) -> dict[str, Any]:
    body={'schema':VERIFICATION_SCHEMA,'status':'passed','task_id':task_id,'transaction_identity':transaction_identity,'performed_verification_set':['unit'],'failed_count':0}
    body['verification_id']='engineering-task-verification-'+fingerprint(body)[:24]
    body['fingerprint']=fingerprint({k:v for k,v in body.items() if k!='fingerprint'})
    return body
