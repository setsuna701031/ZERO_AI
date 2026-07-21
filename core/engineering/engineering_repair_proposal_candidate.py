from __future__ import annotations
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import fingerprint
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_multifile_coding_workflow import REPAIR_AUTHORITY, ITERATION_POLICY, canon, REVIEW_SCHEMA
REPAIR_SCHEMA='zero.engineering.repair_proposal_candidate.v1'

def build_repair_proposal_candidate(*, parent_work_request:Mapping[str,Any], parent_change_package:Mapping[str,Any], parent_execution:Mapping[str,Any], test_failure_evidence:Mapping[str,Any], confirmed_scope:Sequence[str]):
    suspected=test_failure_evidence.get('suspected_related_paths',[]); scope=set(confirmed_scope or [])
    outside=[p['path'] for p in suspected if scope and not any(p['path']==s or p['path'].startswith(str(s).rstrip('/')+'/') for s in scope)]
    rel='requires_scope_expansion' if outside else 'within_confirmed_scope' if suspected else 'unknown'
    return canon({'schema':REPAIR_SCHEMA,'parent_work_request_reference':_ref(parent_work_request),'parent_change_package_reference':_ref(parent_change_package),'parent_execution_reference':_ref(parent_execution),'test_failure_evidence_reference':_ref(test_failure_evidence),'candidate_status':'requires_human_review' if rel!='within_confirmed_scope' else 'ready_for_review','repair_goal':'Investigate bounded failed tests and propose a next governed plan candidate only after human review.','suspected_paths':suspected,'proposed_investigation_steps':['read repository files referenced by bounded traceback','compare failed acceptance criterion mapping','inspect changed paths only within confirmed scope unless human expands scope'],'proposed_change_intents':[{'path':p['path'],'intent':'high level repair intent only; no executable operation'} for p in suspected],'proposed_test_targets':sorted({f.get('test_node') for f in test_failure_evidence.get('failed_tests',[]) if f.get('test_node')}),'scope_relationship':rel,'risk_level':'high' if rel=='requires_scope_expansion' else 'medium','uncertainties':['root cause unconfirmed','human review required before next planning'],'blocking_questions':['Should ZERO enter the next read-only planning iteration?'] if rel!='within_confirmed_scope' else [],'authority':REPAIR_AUTHORITY},'repair_candidate_fingerprint','repair_candidate_id','engineering-repair-candidate-')

def review_repair_candidate(candidate:Mapping[str,Any], review:Mapping[str,Any]):
    if not review.get('human_actor'): raise ValueError('human_actor_required')
    body={'schema':REVIEW_SCHEMA,'repair_candidate_reference':_ref(candidate),'human_actor':review['human_actor'],'decision':review.get('decision'),'approved_investigation_scope':review.get('approved_investigation_scope',[]),'approved_planning_scope':review.get('approved_planning_scope',[]),'approved_test_targets':review.get('approved_test_targets',[]),'notes':review.get('notes',''),'not_approval':True,'not_authorization':True}
    return canon(body,'review_fingerprint','review_id','engineering-repair-review-')

def build_iteration_index(iterations=()):
    return canon({'schema':'zero.engineering.iteration_index.v1','iteration_policy':ITERATION_POLICY,'iterations':list(iterations),'append_only':True},'iteration_index_fingerprint','iteration_index_id','engineering-iteration-index-')
