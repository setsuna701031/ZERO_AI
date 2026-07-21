from __future__ import annotations

from typing import Any, Mapping

from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import CHANGE_PACKAGE_SCHEMA, _ref
from core.engineering.engineering_governed_patch_authoring import snapshot_patch_sources

PREP_SCHEMA='zero.engineering.change_package_preparation_intake.v1'
VALIDATION_SCHEMA='zero.engineering.change_package_candidate_validation.v1'
APPROVAL_SCHEMA='zero.engineering.change_package_approval.v1'
AUTH_REQUEST_SCHEMA='zero.engineering.patch_authorization_request.v1'
AUTH_DECISION_SCHEMA='zero.engineering.patch_authorization_decision.v1'
AUTHORIZED_SCHEMA='zero.engineering.authorized_change_package.v1'
READINESS_SCHEMA='zero.engineering.patch_execution_readiness.v1'
AUTHORITY={'may_modify_repository':False,'may_apply_patch':False,'may_execute':False,'may_approve':False,'may_authorize':False,'may_issue_token':False,'may_commit':False,'may_retry':False,'may_complete':False}
STORE_FILES={'preparation':'change-package/preparation-intake.json','candidate':'change-package/candidate.json','validation':'change-package/validation.json','approval':'change-package/approval.json','request':'authorization/request.json','decision':'authorization/decision.json','authorized':'authorization/authorized-package.json','readiness':'authorization/readiness.json'}
ALLOWED_OPS={'replace_exact_text','replace_file_content','append_text','remove_exact_text','create_text_file'}

class PatchAuthorizationError(ValueError):
    def __init__(self,code): super().__init__(code); self.code=code

def build_change_package_preparation(*,work_request,human_plan_confirmation,reproduction_result,repair_strategy,patch_candidate,human_patch_review,authoring_intake,candidate_diff,authoring_validation,human_authored_patch_review,source_snapshots,repository_identity,workspace_snapshot_reference,confirmed_scope,iteration_reference,session_id):
    if authoring_validation.get('validation_status')!='valid': raise PatchAuthorizationError('authored_patch_validation_required')
    if human_authored_patch_review.get('decision')!='confirmed': raise PatchAuthorizationError('authored_patch_review_not_confirmed')
    if human_authored_patch_review.get('candidate_diff_reference')!=_ref(candidate_diff): raise PatchAuthorizationError('unresolved_candidate_diff')
    body={'schema':PREP_SCHEMA,'session_id':session_id,'iteration_reference':dict(iteration_reference),'work_request_reference':_ref(work_request),'human_plan_confirmation_reference':_ref(human_plan_confirmation),'reproduction_result_reference':_ref(reproduction_result),'repair_strategy_reference':_ref(repair_strategy),'patch_candidate_reference':_ref(patch_candidate),'human_patch_review_reference':_ref(human_patch_review),'patch_authoring_intake_reference':_ref(authoring_intake),'candidate_diff_reference':_ref(candidate_diff),'human_authored_patch_review_reference':_ref(human_authored_patch_review),'source_snapshot_references':[_ref(x) for x in source_snapshots.get('sources',[])],'repository_identity':dict(repository_identity),'workspace_snapshot_reference':dict(workspace_snapshot_reference),'confirmed_scope':list(confirmed_scope),'confirmed_paths':list(human_authored_patch_review.get('confirmed_paths') or candidate_diff.get('ordered_paths') or []),'confirmed_edit_ids':list(human_authored_patch_review.get('confirmed_edit_ids') or []),'confirmed_test_targets':list(human_authored_patch_review.get('confirmed_test_edits') or []),'authority':AUTHORITY}
    return canon(body,'preparation_fingerprint','preparation_id','engineering-change-package-preparation-')

def build_change_package_candidate(preparation,authoring_intake,source_snapshots,file_edits,test_edits,candidate_diff,patch_candidate):
    edits=sorted(list(file_edits.get('edits') or [])+list(test_edits.get('edits') or []),key=lambda x:x['path']); sources={x['path']:x for x in source_snapshots.get('sources',[])}; patch_items={x['path']:x for x in patch_candidate.get('ordered_patch_items',[])}; operation_by_item={patch_items[x['path']].get('patch_item_id'):f'operation-{i:04d}' for i,x in enumerate(edits,1) if x['path'] in patch_items}; operations=[]
    for index,edit in enumerate(edits,1):
        item=patch_items.get(edit['path'],{}); operations.append({'operation_id':f'operation-{index:04d}','path':edit['path'],'operation_type':edit['candidate_edit_kind'],'source_sha256':(sources.get(edit['path']) or {}).get('file_sha256'),'expected_result_sha256':__import__('hashlib').sha256(edit['candidate_content'].encode('utf-8')).hexdigest(),'edit_candidate_reference':_ref(edit),'candidate_content':edit['candidate_content'],'candidate_diff':edit['candidate_diff'],'depends_on':[operation_by_item[d] for d in item.get('depends_on',[]) if d in operation_by_item],'scope_binding':'confirmed','acceptance_criteria':list(edit.get('acceptance_criteria') or []),'verification_targets':list(preparation.get('confirmed_test_targets') or authoring_intake.get('confirmed_test_targets') or [])})
    body={'schema':CHANGE_PACKAGE_SCHEMA,'session_id':preparation.get('session_id'),'iteration_reference':preparation.get('iteration_reference'),'preparation_reference':_ref(preparation),'repository_identity':preparation.get('repository_identity'),'workspace_snapshot_reference':preparation.get('workspace_snapshot_reference'),'source_snapshot_references':preparation.get('source_snapshot_references'),'candidate_diff_reference':_ref(candidate_diff),'package_status':'candidate','execution_authority':'not_granted','ordered_operations':operations,'ordered_paths':[x['path'] for x in operations],'operation_count':len(operations),'confirmed_scope':list(preparation.get('confirmed_scope') or []),'acceptance_criterion_mappings':patch_candidate.get('acceptance_criterion_mappings',[]),'verification_plan':{'targets':sorted({t for x in operations for t in x.get('verification_targets',[])}),'bounded':True,'maximum_targets':8,'timeout_seconds':120},'rollback_plan':{'strategy':'restore source snapshot bytes after separately authorized apply failure','source_snapshot_references':preparation.get('source_snapshot_references'),'required':True},'risk_summary':'candidate package; explicit human approval and authorization required','authority':AUTHORITY}
    return canon(body,'change_package_fingerprint','change_package_id','engineering-governed-change-package-')

def validate_change_package_candidate(package,*,preparation=None,candidate_diff=None,source_snapshots=None,file_edits=None,test_edits=None,human_authored_patch_review=None,patch_candidate=None,authoring_intake=None,workspace_root='.',repository_identity=None,session_id=None,iteration_reference=None):
    errors=[]; material={k:v for k,v in package.items() if k not in {'change_package_fingerprint','change_package_id'}}; expected=canon(material,'change_package_fingerprint','change_package_id','engineering-governed-change-package-')
    if expected!=package: errors.append('package_fingerprint_mismatch')
    if not human_authored_patch_review: errors.append('missing_authored_patch_review')
    elif human_authored_patch_review.get('decision')!='confirmed': errors.append('authored_patch_review_not_confirmed')
    if not candidate_diff: errors.append('missing_candidate_diff')
    elif package.get('candidate_diff_reference')!=_ref(candidate_diff): errors.append('wrong_candidate_diff_fingerprint')
    if not source_snapshots: errors.append('missing_source_snapshot')
    elif any(not x.get('source_sha256') for x in package.get('ordered_operations') or []): errors.append('source_snapshot_unresolved')
    if preparation and package.get('preparation_reference')!=_ref(preparation): errors.append('stale_patch_authoring_artifact')
    if repository_identity is not None and dict(package.get('repository_identity') or {})!=dict(repository_identity): errors.append('wrong_repository_identity')
    if session_id and package.get('session_id')!=session_id: errors.append('session_mismatch')
    if iteration_reference is not None and package.get('iteration_reference')!=dict(iteration_reference): errors.append('iteration_mismatch')
    try:
        current=snapshot_patch_sources(authoring_intake or {},patch_candidate or {},workspace_root=workspace_root)
        if source_snapshots and current.get('source_set_fingerprint')!=source_snapshots.get('source_set_fingerprint'): errors.extend(['source_fingerprint_mismatch','workspace_drift'])
    except Exception: errors.append('workspace_drift')
    ops=package.get('ordered_operations') or []; paths=[x.get('path') for x in ops]; scope=package.get('confirmed_scope') or []
    edits=list((file_edits or {}).get('edits') or [])+list((test_edits or {}).get('edits') or []); refs={str(_ref(x)) for x in edits}
    if len(edits)!=len(ops) or any(x.get('expected_result_sha256')!=__import__('hashlib').sha256(str(e.get('candidate_content','')).encode('utf-8')).hexdigest() for x,e in zip(ops,sorted(edits,key=lambda y:y.get('path','')))): errors.append('candidate_diff_mismatch')
    if preparation and list(package.get('confirmed_scope') or [])!=list(preparation.get('confirmed_scope') or []): errors.append('scope_mismatch')
    if package.get('operation_count')!=len(ops): errors.append('operation_count_mismatch')
    if package.get('ordered_paths')!=paths: errors.append('ordered_path_mismatch')
    if any(x.get('operation_type') not in ALLOWED_OPS for x in ops): errors.append('unknown_operation')
    if any(str(x.get('edit_candidate_reference')) not in refs for x in ops): errors.append('unconfirmed_operation')
    if any(not any(p==s or str(p).startswith(str(s).rstrip('/')+'/') for s in scope) for p in paths): errors.append('silent_scope_expansion')
    if any(not x.get('acceptance_criteria') for x in ops): errors.append('missing_acceptance_mapping')
    ids={x.get('operation_id') for x in ops}; temp=set(); done=set()
    def visit(i):
        if i in temp: raise PatchAuthorizationError('dependency_cycle')
        if i in done:return
        temp.add(i); op=next((x for x in ops if x.get('operation_id')==i),None)
        if not op: raise PatchAuthorizationError('dependency_cycle')
        for d in op.get('depends_on') or []: visit(d)
        temp.remove(i);done.add(i)
    try:
        for i in ids: visit(i)
    except PatchAuthorizationError: errors.append('dependency_cycle')
    verify=package.get('verification_plan') or {}
    if not verify.get('bounded') or len(verify.get('targets') or [])>8 or int(verify.get('timeout_seconds') or 0)>120: errors.append('unbounded_verification_plan')
    if not (package.get('rollback_plan') or {}).get('required'): errors.append('missing_rollback_plan')
    if any(package.get('authority',{}).get(k) for k in AUTHORITY) or package.get('execution_authority')!='not_granted': errors.append('authority_payload_rejection')
    body={'schema':VALIDATION_SCHEMA,'change_package_candidate_reference':_ref(package),'valid':not errors,'validation_status':'valid' if not errors else 'invalid','reason_codes':sorted(set(errors)),'authority':AUTHORITY}
    return canon(body,'package_validation_fingerprint','package_validation_id','engineering-package-validation-')

def review_change_package(package,validation,review):
    if not review.get('human_actor'): raise PatchAuthorizationError('human_actor_required')
    if review.get('change_package_candidate_reference')!=_ref(package): raise PatchAuthorizationError('stale_approval')
    decision=review.get('decision')
    if decision not in {'approved','rejected','requires_revision'}: raise PatchAuthorizationError('invalid_approval_decision')
    if decision=='approved' and validation.get('validation_status')!='valid': raise PatchAuthorizationError('invalid_change_package')
    if decision=='approved' and (list(review.get('approved_paths') or [])!=list(package.get('ordered_paths') or []) or list(review.get('approved_operation_ids') or [])!=[x.get('operation_id') for x in package.get('ordered_operations',[])]): raise PatchAuthorizationError('approval_scope_mismatch')
    if decision=='approved' and not review.get('scope_acknowledgement'): raise PatchAuthorizationError('scope_acknowledgement_required')
    body={'schema':APPROVAL_SCHEMA,'change_package_candidate_reference':_ref(package),'package_validation_reference':_ref(validation),'human_actor':review['human_actor'],'decision':decision,'approved_paths':list(review.get('approved_paths') or []),'approved_operation_ids':list(review.get('approved_operation_ids') or []),'approved_test_targets':list(review.get('approved_test_targets') or []),'risk_acknowledgements':list(review.get('risk_acknowledgements') or []),'scope_acknowledgement':bool(review.get('scope_acknowledgement')),'conditions':list(review.get('conditions') or []),'notes':review.get('notes',''),'not_authorization':True,'not_execution':True}
    return canon(body,'approval_fingerprint','approval_id','engineering-package-approval-')

def revise_change_package_candidate(package,revision):
    if not revision.get('human_actor'): raise PatchAuthorizationError('human_actor_required')
    if revision.get('change_package_candidate_reference')!=_ref(package): raise PatchAuthorizationError('stale_revision_request')
    if not revision.get('revision_reason'): raise PatchAuthorizationError('revision_reason_required')
    allowed={'risk_summary','verification_plan','rollback_plan'}
    updates=dict(revision.get('updates') or {})
    if set(updates)-allowed: raise PatchAuthorizationError('revision_scope_expansion')
    body={k:v for k,v in package.items() if k not in {'change_package_fingerprint','change_package_id'}}
    body.update(updates)
    body['previous_change_package_reference']=_ref(package)
    body['revision_reason']=revision['revision_reason']
    body['package_status']='candidate'
    body['execution_authority']='not_granted'
    body['authority']=AUTHORITY
    return canon(body,'change_package_fingerprint','change_package_id','engineering-governed-change-package-')

def build_authorization_request(package,approval,*,requested_executor='zero-governed-patch-executor-v1'):
    if approval.get('decision')!='approved': raise PatchAuthorizationError('approval_required')
    if approval.get('change_package_candidate_reference')!=_ref(package): raise PatchAuthorizationError('stale_approval')
    body={'schema':AUTH_REQUEST_SCHEMA,'approved_change_package_reference':_ref(package),'approval_reference':_ref(approval),'repository_identity':package.get('repository_identity'),'workspace_snapshot_reference':package.get('workspace_snapshot_reference'),'authorized_scope_request':list(package.get('confirmed_scope') or []),'authorized_operation_ids':[x['operation_id'] for x in package.get('ordered_operations',[])],'authorized_paths':list(package.get('ordered_paths') or []),'authorized_test_targets':list(package.get('verification_plan',{}).get('targets') or []),'requested_validity':'same_session_same_iteration_until_single_use','requested_use_count':1,'requested_executor':requested_executor,'risk_summary':package.get('risk_summary'),'authority':AUTHORITY}
    return canon(body,'authorization_request_fingerprint','authorization_request_id','engineering-patch-authorization-request-')

def decide_patch_authorization(request,package,approval,decision):
    if not decision.get('human_actor'): raise PatchAuthorizationError('human_actor_required')
    if decision.get('authorization_request_reference')!=_ref(request) or request.get('approved_change_package_reference')!=_ref(package): raise PatchAuthorizationError('stale_authorization')
    if approval.get('decision')!='approved' or request.get('approval_reference')!=_ref(approval): raise PatchAuthorizationError('stale_approval')
    state=decision.get('decision')
    if state not in {'authorized','rejected','requires_revision'}: raise PatchAuthorizationError('invalid_authorization_decision')
    if state=='authorized':
        for supplied,requested,code in (('authorized_scope','authorized_scope_request','scope_expansion'),('authorized_operation_ids','authorized_operation_ids','operation_substitution'),('authorized_paths','authorized_paths','path_substitution'),('authorized_test_targets','authorized_test_targets','test_target_substitution')):
            if supplied in decision and list(decision.get(supplied) or [])!=list(request.get(requested) or []): raise PatchAuthorizationError(code)
    body={'schema':AUTH_DECISION_SCHEMA,'authorization_request_reference':_ref(request),'approval_reference':_ref(approval),'change_package_reference':_ref(package),'human_actor':decision['human_actor'],'decision':state,'authorized_scope':list(decision.get('authorized_scope') or request.get('authorized_scope_request') or []),'authorized_operation_ids':list(decision.get('authorized_operation_ids') or request.get('authorized_operation_ids') or []),'authorized_paths':list(decision.get('authorized_paths') or request.get('authorized_paths') or []),'authorized_test_targets':list(decision.get('authorized_test_targets') or request.get('authorized_test_targets') or []),'validity_policy':'same_session_same_iteration_until_single_use','single_use':True,'conditions':list(decision.get('conditions') or []),'notes':decision.get('notes',''),'not_execution':True}
    return canon(body,'authorization_fingerprint','authorization_id','engineering-patch-authorization-')

def build_authorized_change_package(package,approval,authorization):
    if authorization.get('decision')!='authorized': raise PatchAuthorizationError('authorization_required')
    if authorization.get('change_package_reference')!=_ref(package): raise PatchAuthorizationError('package_fingerprint_mismatch')
    if authorization.get('approval_reference')!=_ref(approval) or approval.get('change_package_candidate_reference')!=_ref(package): raise PatchAuthorizationError('stale_approval')
    op_ids=[x['operation_id'] for x in package.get('ordered_operations',[])]; paths=package.get('ordered_paths') or []
    if authorization.get('authorized_operation_ids')!=op_ids: raise PatchAuthorizationError('operation_substitution')
    if authorization.get('authorized_paths')!=paths: raise PatchAuthorizationError('path_substitution')
    if authorization.get('authorized_scope')!=package.get('confirmed_scope'): raise PatchAuthorizationError('scope_expansion')
    if authorization.get('authorized_test_targets')!=package.get('verification_plan',{}).get('targets'): raise PatchAuthorizationError('test_target_substitution')
    body={'schema':AUTHORIZED_SCHEMA,'change_package_reference':_ref(package),'approval_reference':_ref(approval),'authorization_reference':_ref(authorization),'session_id':package.get('session_id'),'iteration_reference':package.get('iteration_reference'),'repository_identity':package.get('repository_identity'),'workspace_snapshot_reference':package.get('workspace_snapshot_reference'),'authorized_scope':authorization.get('authorized_scope'),'authorized_operation_ids':op_ids,'authorized_paths':paths,'authorized_test_targets':authorization.get('authorized_test_targets'),'single_use':True,'authorization_status':'granted','execution_status':'not_started','replay_status':'unused','authority':{**AUTHORITY,'eligible_for_explicit_apply':True}}
    return canon(body,'authorized_package_fingerprint','authorized_package_id','engineering-authorized-package-')

def verify_patch_readiness(authorized,package,approval,authorization,*,source_snapshots,authoring_intake,patch_candidate,workspace_root='.'):
    errors=[]
    if authorized.get('replay_status')!='unused': errors.extend(['authorization_already_used','authorization_replay'])
    if authorized.get('change_package_reference')!=_ref(package): errors.append('package_fingerprint_mismatch')
    if authorized.get('approval_reference')!=_ref(approval): errors.append('stale_approval')
    if authorized.get('authorization_reference')!=_ref(authorization): errors.append('stale_authorization')
    try:
        current=snapshot_patch_sources(authoring_intake,patch_candidate,workspace_root=workspace_root)
        if current.get('source_set_fingerprint')!=source_snapshots.get('source_set_fingerprint'): errors.extend(['workspace_drift','source_snapshot_drift'])
    except Exception: errors.append('workspace_drift')
    status='ready_for_explicit_apply' if not errors else 'blocked'
    body={'schema':READINESS_SCHEMA,'authorized_change_package_reference':_ref(authorized),'change_package_reference':_ref(package),'approval_reference':_ref(approval),'authorization_reference':_ref(authorization),'readiness_status':status,'reason_codes':sorted(set(errors)),'verification_plan_present':bool(package.get('verification_plan')),'rollback_plan_present':bool(package.get('rollback_plan')),'executor':'not_invoked','next_governed_action':'awaiting_explicit_apply' if not errors else 'resolve_readiness_blockers','authority':AUTHORITY}
    return canon(body,'readiness_fingerprint','readiness_id','engineering-patch-readiness-')

def inspect_patch_authorization_state(bundle):
    get=lambda k:bundle.get(STORE_FILES[k]) or {}
    return {'authored_patch_review_status':(bundle.get('patch-authoring/review.json') or {}).get('decision','not_started'),'change_package_preparation_status':'created' if get('preparation') else 'missing','change_package_candidate_status':get('candidate').get('package_status','missing'),'change_package_validation_status':get('validation').get('validation_status','not_started'),'human_package_approval_status':get('approval').get('decision','not_started'),'authorization_request_status':'created' if get('request') else 'missing','human_authorization_status':get('decision').get('decision','not_started'),'authorized_package_status':get('authorized').get('authorization_status','not_started'),'authorization_use_status':get('authorized').get('replay_status','not_started'),'workspace_drift_status':'detected' if 'workspace_drift' in get('readiness').get('reason_codes',[]) else 'not_detected' if get('readiness') else 'not_checked','execution_readiness_status':get('readiness').get('readiness_status','not_started'),'next_governed_action':resume_patch_authorization_state(bundle)['decision']}

def resume_patch_authorization_state(bundle):
    if not bundle.get('patch-authoring/review.json'):d='requires_human_authored_patch_review'
    elif not bundle.get(STORE_FILES['preparation']):d='requires_change_package_preparation'
    elif not bundle.get(STORE_FILES['candidate']):d='requires_change_package_candidate'
    elif not bundle.get(STORE_FILES['validation']):d='requires_change_package_validation'
    elif not bundle.get(STORE_FILES['approval']):d='requires_human_change_package_approval'
    elif (bundle.get(STORE_FILES['approval']) or {}).get('decision')!='approved':d='requires_approved_change_package'
    elif not bundle.get(STORE_FILES['request']):d='requires_authorization_request'
    elif not bundle.get(STORE_FILES['decision']):d='requires_human_authorization'
    elif (bundle.get(STORE_FILES['decision']) or {}).get('decision')!='authorized':d='requires_authorized_decision'
    elif not bundle.get(STORE_FILES['authorized']):d='requires_authorized_change_package'
    elif not bundle.get(STORE_FILES['readiness']):d='requires_execution_readiness_verification'
    else:d='awaiting_explicit_apply'
    return {'schema':'zero.engineering.patch_authorization_resume.v1','decision':d,'will_approve':False,'will_authorize':False,'will_issue_token':False,'will_apply_patch':False,'will_modify_repository':False,'will_execute_tests':False,'will_commit':False,'will_push':False,'will_retry':False,'will_complete':False}
