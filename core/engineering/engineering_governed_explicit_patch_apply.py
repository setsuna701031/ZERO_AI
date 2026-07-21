from __future__ import annotations

import hashlib, os, time
from pathlib import Path
from typing import Any, Mapping

from core.engineering.engineering_governed_patch_authorization import AUTHORITY
from core.engineering.engineering_governed_patch_authoring import snapshot_patch_sources
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref, run_bounded_test_operation, safe_path

REQUEST_SCHEMA='zero.engineering.explicit_patch_apply_request.v1'
ADMISSION_SCHEMA='zero.engineering.patch_apply_admission.v1'
USAGE_SCHEMA='zero.engineering.patch_authorization_usage.v1'
TRANSACTION_SCHEMA='zero.engineering.patch_apply_transaction.v1'
EVIDENCE_SCHEMA='zero.engineering.patch_operation_evidence.v1'
RESULT_SCHEMA='zero.engineering.explicit_patch_apply_result.v1'
VERIFY_SCHEMA='zero.engineering.patch_apply_verification_result.v1'
COMPLETION_SCHEMA='zero.engineering.patch_completion_review_candidate.v1'
REVIEW_SCHEMA='zero.engineering.patch_completion_review.v1'
STORE_FILES={'request':'apply/request.json','admission':'apply/admission.json','usage':'apply/authorization-usage.json','transaction':'apply/transaction.json','evidence':'apply/operation-evidence.json','result':'apply/result.json','verification':'apply/verification-result.json','completion':'apply/completion-candidate.json','review':'apply/completion-review.json'}
ALLOWED_OPS={'replace_exact_text','replace_file_content','append_text','remove_exact_text','create_text_file'}

class ExplicitPatchApplyError(ValueError):
    def __init__(self,code): super().__init__(code); self.code=code

def _sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _file_state(path:Path)->dict[str,Any]:
    raw=path.read_bytes(); text=raw.decode('utf-8'); return {'sha256':_sha(raw),'size':len(raw),'encoding':'utf-8','newline_style':'crlf' if '\r\n' in text else 'lf' if '\n' in text else 'none'}

def build_explicit_apply_request(authorized,readiness,approval,authorization,request):
    if not request.get('human_actor'): raise ExplicitPatchApplyError('missing_human_actor')
    decision=request.get('decision')
    if decision not in {'confirmed','rejected','requires_revision'}: raise ExplicitPatchApplyError('invalid_apply_decision')
    package_ref=authorized.get('change_package_reference')
    if request.get('authorized_change_package_reference')!=_ref(authorized): raise ExplicitPatchApplyError('wrong_authorization_reference')
    if request.get('execution_readiness_reference')!=_ref(readiness): raise ExplicitPatchApplyError('readiness_not_ready')
    body={'schema':REQUEST_SCHEMA,'authorized_change_package_reference':_ref(authorized),'execution_readiness_reference':_ref(readiness),'approval_reference':_ref(approval),'authorization_reference':_ref(authorization),'change_package_reference':package_ref,'human_actor':request['human_actor'],'decision':decision,'confirmed_package_fingerprint':request.get('confirmed_package_fingerprint'),'confirmed_operation_ids':list(request.get('confirmed_operation_ids') or []),'confirmed_paths':list(request.get('confirmed_paths') or []),'confirmed_test_targets':list(request.get('confirmed_test_targets') or []),'workspace_snapshot_acknowledgement':bool(request.get('workspace_snapshot_acknowledgement')),'source_snapshot_acknowledgements':list(request.get('source_snapshot_acknowledgements') or []),'rollback_acknowledgement':bool(request.get('rollback_acknowledgement')),'risk_acknowledgements':list(request.get('risk_acknowledgements') or []),'notes':request.get('notes',''),'authority':AUTHORITY}
    return canon(body,'apply_request_fingerprint','apply_request_id','engineering-explicit-apply-request-')

def admit_patch_apply(request,authorized,readiness,package,approval,authorization,*,source_snapshots,authoring_intake,patch_candidate,workspace_root='.'):
    errors=[]
    if not request: errors.append('missing_explicit_apply_request')
    elif request.get('decision')!='confirmed': errors.append('apply_request_not_confirmed')
    if approval.get('decision')!='approved': errors.append('approval_not_approved')
    if authorization.get('decision')!='authorized' or authorized.get('authorization_status')!='granted': errors.append('authorization_not_granted')
    if request.get('authorized_change_package_reference')!=_ref(authorized) or authorized.get('authorization_reference')!=_ref(authorization): errors.append('wrong_authorization_reference')
    if request.get('execution_readiness_reference')!=_ref(readiness): errors.append('readiness_not_ready')
    if request.get('approval_reference')!=_ref(approval) or authorized.get('approval_reference')!=_ref(approval): errors.append('stale_approval')
    if request.get('authorization_reference')!=_ref(authorization): errors.append('stale_authorization')
    if authorized.get('change_package_reference')!=_ref(package): errors.append('wrong_package_fingerprint')
    if authorized.get('session_id') is not None and authorized.get('session_id')!=package.get('session_id'): errors.append('session_mismatch')
    if authorized.get('iteration_reference') is not None and authorized.get('iteration_reference')!=package.get('iteration_reference'): errors.append('iteration_mismatch')
    if authorized.get('repository_identity') is not None and authorized.get('repository_identity')!=package.get('repository_identity'): errors.append('repository_identity_mismatch')
    if authorized.get('replay_status')!='unused': errors.extend(['authorization_already_used','authorization_replay'])
    if readiness.get('readiness_status')!='ready_for_explicit_apply': errors.append('readiness_not_ready')
    if request.get('confirmed_package_fingerprint')!=package.get('change_package_fingerprint'): errors.append('wrong_package_fingerprint')
    op_ids=[x.get('operation_id') for x in package.get('ordered_operations',[])]; paths=list(package.get('ordered_paths') or []); targets=list(package.get('verification_plan',{}).get('targets') or [])
    if request.get('confirmed_operation_ids')!=op_ids: errors.append('operation_substitution')
    if request.get('confirmed_paths')!=paths: errors.append('path_substitution')
    if request.get('confirmed_test_targets')!=targets: errors.append('verification_target_not_authorized')
    if request.get('source_snapshot_acknowledgements')!=package.get('source_snapshot_references'): errors.append('source_snapshot_drift')
    if authorized.get('authorized_scope') is not None and authorized.get('authorized_scope')!=package.get('confirmed_scope'): errors.append('scope_mismatch')
    if not request.get('workspace_snapshot_acknowledgement') or not request.get('rollback_acknowledgement'): errors.append('missing_apply_acknowledgement')
    if len(package.get('ordered_operations') or [])!=package.get('operation_count'): errors.append('operation_count_mismatch')
    if any(x.get('operation_type') not in ALLOWED_OPS for x in package.get('ordered_operations',[])): errors.append('unsupported_operation')
    try:
        current=snapshot_patch_sources(authoring_intake,patch_candidate,workspace_root=workspace_root)
        if current.get('source_set_fingerprint')!=source_snapshots.get('source_set_fingerprint'): errors.extend(['workspace_drift','source_snapshot_drift'])
    except Exception: errors.append('workspace_drift')
    body={'schema':ADMISSION_SCHEMA,'explicit_apply_request_reference':_ref(request),'authorized_package_reference':_ref(authorized),'change_package_reference':_ref(package),'authorization_reference':_ref(authorization),'repository_identity':package.get('repository_identity'),'session_id':package.get('session_id'),'iteration_reference':package.get('iteration_reference'),'admission_status':'admitted' if not errors else 'blocked','reason_codes':sorted(set(errors)),'reserved_package_fingerprint':package.get('change_package_fingerprint'),'reserved_operation_ids':op_ids,'reserved_paths':paths,'authorization_usage':'unreserved','mutation_performed':False,'authority':AUTHORITY}
    return canon(body,'apply_admission_fingerprint','apply_admission_id','engineering-patch-apply-admission-')

def reserve_authorization(admission,authorized,authorization):
    if admission.get('admission_status')!='admitted': raise ExplicitPatchApplyError('apply_not_admitted')
    if authorized.get('replay_status')!='unused': raise ExplicitPatchApplyError('authorization_already_used')
    body={'schema':USAGE_SCHEMA,'apply_admission_reference':_ref(admission),'authorized_package_reference':_ref(authorized),'authorization_reference':_ref(authorization),'session_id':admission.get('session_id'),'iteration_reference':admission.get('iteration_reference'),'package_fingerprint':admission.get('reserved_package_fingerprint'),'operation_ids':admission.get('reserved_operation_ids'),'execution_attempt_id':'apply-'+admission['apply_admission_id'],'authorization_usage':'reserved','use_count':0,'manual_reauthorization_required':False,'authority':AUTHORITY}
    return canon(body,'authorization_usage_fingerprint','authorization_usage_id','engineering-authorization-usage-')

def apply_authorized_patch(admission,usage,authorized,package,*,workspace_root='.'):
    if admission.get('admission_status')!='admitted': raise ExplicitPatchApplyError('apply_not_admitted')
    if usage.get('authorization_usage')!='reserved' or usage.get('package_fingerprint')!=package.get('change_package_fingerprint'): raise ExplicitPatchApplyError('authorization_reserved_elsewhere')
    root=Path(workspace_root).resolve(); ops=package.get('ordered_operations') or []; backups={}; evidence=[]; failed=None; rollback='not_required'; started=time.monotonic()
    transaction=canon({'schema':TRANSACTION_SCHEMA,'apply_admission_reference':_ref(admission),'authorization_usage_reference':_ref(usage),'operation_ids':[x.get('operation_id') for x in ops],'transaction_status':'started','rollback_available':True,'authority':AUTHORITY},'transaction_fingerprint','transaction_id','engineering-patch-transaction-')
    try:
        for op in ops:
            rel=op.get('path',''); target=safe_path(root,rel)
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p!=root): raise ExplicitPatchApplyError('symlink_operation')
            typ=op.get('operation_type'); exists=target.exists()
            if typ=='create_text_file' and exists: raise ExplicitPatchApplyError('unexpected_target_file_exists')
            if typ!='create_text_file' and not exists: raise ExplicitPatchApplyError('target_file_missing')
            if exists:
                state=_file_state(target)
                if state['sha256']!=op.get('source_sha256'): raise ExplicitPatchApplyError('source_hash_mismatch')
                backups[rel]=target.read_bytes()
            else: backups[rel]=None
            source=backups[rel].decode('utf-8') if backups[rel] is not None else ''
            if typ=='replace_exact_text' and op.get('old_text') is not None:
                old=str(op.get('old_text')); count=source.count(old)
                if count!=1: raise ExplicitPatchApplyError('exact_match_not_unique')
                content=source.replace(old,str(op.get('new_text','')),1)
            elif typ=='remove_exact_text' and op.get('old_text') is not None:
                old=str(op.get('old_text')); count=source.count(old)
                if count!=1: raise ExplicitPatchApplyError('exact_match_not_unique')
                content=source.replace(old,'',1)
            elif typ=='append_text' and op.get('append_text') is not None: content=source+str(op.get('append_text'))
            else: content=str(op.get('candidate_content',''))
            raw=content.encode('utf-8')
            if _sha(raw)!=op.get('expected_result_sha256'): raise ExplicitPatchApplyError('expected_result_hash_mismatch')
            target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw); actual=_file_state(target)
            row={'schema':EVIDENCE_SCHEMA,'operation_id':op.get('operation_id'),'path':rel,'operation_type':typ,'pre_sha256':op.get('source_sha256'),'expected_post_sha256':op.get('expected_result_sha256'),'actual_post_sha256':actual['sha256'],'status':'applied','bytes_before':len(backups[rel] or b''),'bytes_after':actual['size'],'encoding':actual['encoding'],'newline_style':actual['newline_style'],'started_reference':transaction['transaction_id'],'completed_reference':transaction['transaction_id'],'failure_reason':None,'rollback_status':'not_required'}
            evidence.append(canon(row,'operation_evidence_fingerprint','operation_evidence_id','engineering-operation-evidence-'))
    except Exception as exc:
        failed=ops[len(evidence)].get('operation_id') if len(evidence)<len(ops) else None
        failure_code=str(getattr(exc,'code',exc))
        rollback='rolled_back'
        try:
            for rel,data in backups.items():
                path=safe_path(root,rel)
                if data is None:
                    if path.exists(): path.unlink()
                else: path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            evidence=[canon({**{k:v for k,v in row.items() if k not in {'operation_evidence_fingerprint','operation_evidence_id'}},'rollback_status':'rolled_back'},'operation_evidence_fingerprint','operation_evidence_id','engineering-operation-evidence-') for row in evidence]
        except Exception: rollback='rollback_failed'
        failed_op=next((x for x in ops if x.get('operation_id')==failed),{})
        failed_row={'schema':EVIDENCE_SCHEMA,'operation_id':failed,'path':failed_op.get('path'),'operation_type':failed_op.get('operation_type'),'pre_sha256':failed_op.get('source_sha256'),'expected_post_sha256':failed_op.get('expected_result_sha256'),'actual_post_sha256':None,'status':'failed','bytes_before':0,'bytes_after':0,'encoding':'utf-8','newline_style':None,'started_reference':transaction['transaction_id'],'completed_reference':transaction['transaction_id'],'failure_reason':failure_code,'rollback_status':rollback}
        evidence.append(canon(failed_row,'operation_evidence_fingerprint','operation_evidence_id','engineering-operation-evidence-'))
        mutation='rollback_failed' if rollback=='rollback_failed' else 'rolled_back'
        limitations=[failure_code]
    else: mutation='applied'; limitations=[]
    usage_body={k:v for k,v in usage.items() if k not in {'authorization_usage_fingerprint','authorization_usage_id'}}; usage_body.update({'authorization_usage':'consumed','use_count':1,'manual_reauthorization_required':mutation!='applied'}); usage2=canon(usage_body,'authorization_usage_fingerprint','authorization_usage_id','engineering-authorization-usage-')
    tx_body={k:v for k,v in transaction.items() if k not in {'transaction_fingerprint','transaction_id'}}; tx_body.update({'transaction_status':'committed' if mutation=='applied' else mutation,'rollback_status':rollback}); transaction=canon(tx_body,'transaction_fingerprint','transaction_id','engineering-patch-transaction-')
    result=canon({'schema':RESULT_SCHEMA,'apply_request_reference':admission.get('explicit_apply_request_reference'),'apply_admission_reference':_ref(admission),'authorized_package_reference':_ref(authorized),'authorization_usage_reference':_ref(usage2),'repository_identity':package.get('repository_identity'),'pre_workspace_snapshot_reference':package.get('workspace_snapshot_reference'),'post_workspace_snapshot_reference':{'changed_paths':list(package.get('ordered_paths') or []) if mutation=='applied' else []},'operation_evidence_references':[_ref(x) for x in evidence],'mutation_status':mutation,'rollback_status':rollback,'changed_paths':list(package.get('ordered_paths') or []) if mutation=='applied' else [],'unchanged_paths':[] if mutation=='applied' else list(package.get('ordered_paths') or []),'failed_operation_id':failed,'limitations':limitations,'duration_seconds':round(time.monotonic()-started,3),'authority':AUTHORITY},'apply_result_fingerprint','apply_result_id','engineering-explicit-apply-result-')
    return transaction,evidence,usage2,result

def verify_applied_patch(result,package,*,workspace_root='.'):
    if result.get('mutation_status')!='applied':
        body={'schema':VERIFY_SCHEMA,'apply_result_reference':_ref(result),'verification_plan_reference':_ref(package.get('verification_plan',{})),'test_result_references':[],'workspace_snapshot_reference':result.get('post_workspace_snapshot_reference'),'verification_status':'blocked','acceptance_criterion_results':[],'regression_status':'not_executed','limitations':['mutation_not_applied'],'completion_eligible':False,'authority':AUTHORITY}; return [],canon(body,'verification_fingerprint','verification_id','engineering-apply-verification-')
    targets=list(package.get('verification_plan',{}).get('targets') or [])
    if not targets or len(targets)>8: raise ExplicitPatchApplyError('unbounded_verification_request')
    op={'operation_type':'run_bounded_test','test_targets':targets,'flags':['-q'],'timeout_seconds':min(int(package.get('verification_plan',{}).get('timeout_seconds') or 120),120)}
    test=run_bounded_test_operation(op,Path(workspace_root)); status='passed' if test.get('status')=='passed' else test.get('status','failed')
    body={'schema':VERIFY_SCHEMA,'apply_result_reference':_ref(result),'verification_plan_reference':_ref(package.get('verification_plan',{})),'test_result_references':[_ref(test)],'workspace_snapshot_reference':result.get('post_workspace_snapshot_reference'),'verification_status':status,'acceptance_criterion_results':package.get('acceptance_criterion_mappings',[]),'regression_status':status,'limitations':[] if status=='passed' else ['focused_verification_not_passed'],'completion_eligible':status=='passed','authority':AUTHORITY}
    return [test],canon(body,'verification_fingerprint','verification_id','engineering-apply-verification-')

def build_completion_review_candidate(result,verification,evidence):
    if verification.get('verification_status')=='passed': recommendation='eligible_for_human_completion_review'
    elif result.get('rollback_status')=='rollback_failed': recommendation='requires_rollback_review'
    elif result.get('mutation_status')=='applied': recommendation='requires_repair_review'
    else: recommendation='blocked'
    body={'schema':COMPLETION_SCHEMA,'apply_result_reference':_ref(result),'verification_result_reference':_ref(verification),'changed_paths':result.get('changed_paths',[]),'operation_summary':[{'operation_id':x.get('operation_id'),'status':x.get('status')} for x in evidence],'test_summary':verification.get('regression_status'),'acceptance_summary':verification.get('acceptance_criterion_results',[]),'remaining_risks':verification.get('limitations',[]),'rollback_availability':True,'completion_recommendation':recommendation,'authority':AUTHORITY}
    return canon(body,'completion_candidate_fingerprint','completion_candidate_id','engineering-completion-candidate-')

def review_completion(candidate,review):
    if not review.get('human_actor'): raise ExplicitPatchApplyError('missing_human_actor')
    if review.get('completion_candidate_reference')!=_ref(candidate): raise ExplicitPatchApplyError('stale_completion_candidate')
    if review.get('decision') not in {'completed','rejected','requires_repair','requires_rollback'}: raise ExplicitPatchApplyError('invalid_completion_decision')
    body={'schema':REVIEW_SCHEMA,'completion_candidate_reference':_ref(candidate),'human_actor':review['human_actor'],'decision':review['decision'],'notes':review.get('notes',''),'commit_authority':False,'push_authority':False,'authority':AUTHORITY}
    return canon(body,'completion_review_fingerprint','completion_review_id','engineering-completion-review-')

def inspect_explicit_apply_state(bundle):
    get=lambda k:bundle.get(STORE_FILES[k]) or {}
    return {'explicit_apply_request_status':get('request').get('decision','not_started'),'apply_admission_status':get('admission').get('admission_status','not_started'),'authorization_usage_status':get('usage').get('authorization_usage','unused'),'transaction_status':get('transaction').get('transaction_status','not_started'),'operation_progress':len(get('evidence').get('operations',[])) if isinstance(get('evidence'),dict) else 0,'rollback_status':get('result').get('rollback_status','not_started'),'mutation_result_status':get('result').get('mutation_status','not_started'),'verification_status':get('verification').get('verification_status','not_started'),'completion_review_candidate_status':get('completion').get('completion_recommendation','not_started'),'human_completion_review_status':get('review').get('decision','not_started'),'next_governed_action':resume_explicit_apply_state(bundle)['decision']}

def resume_explicit_apply_state(bundle):
    if not bundle.get(STORE_FILES['request']): d='requires_explicit_apply_request'
    elif (bundle.get(STORE_FILES['request']) or {}).get('decision')!='confirmed': d='requires_confirmed_apply_request'
    elif not bundle.get(STORE_FILES['admission']): d='requires_apply_admission'
    elif (bundle.get(STORE_FILES['admission']) or {}).get('admission_status')!='admitted': d='requires_admission_remediation'
    elif not bundle.get(STORE_FILES['result']): d='requires_separate_apply_command'
    elif not bundle.get(STORE_FILES['verification']): d='requires_separate_verification_command'
    elif not bundle.get(STORE_FILES['completion']): d='requires_completion_review_candidate'
    elif not bundle.get(STORE_FILES['review']): d='requires_human_completion_review'
    else: d='human_completion_review_recorded'
    return {'schema':'zero.engineering.explicit_apply_resume.v1','decision':d,'will_apply':False,'will_retry':False,'will_rollback':False,'will_run_tests':False,'will_complete':False,'will_commit':False,'will_push':False}
