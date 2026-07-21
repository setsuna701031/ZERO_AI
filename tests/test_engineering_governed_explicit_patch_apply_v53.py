from __future__ import annotations

import copy, hashlib, subprocess, sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_explicit_patch_apply import *
from core.engineering.engineering_governed_patch_authoring import snapshot_patch_sources
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact

def art(schema,name,**extra): return canon({'schema':schema,**extra},f'{name}_fingerprint',f'{name}_id',f'engineering-{name}-')
def sha(text): return hashlib.sha256(text.encode()).hexdigest()

def prepared(tmp_path,two=False):
    root=tmp_path/'repo'; (root/'app').mkdir(parents=True); (root/'tests').mkdir()
    (root/'app/value.py').write_text('VALUE = 1\n',encoding='utf-8',newline='')
    (root/'tests/test_value.py').write_text('from app.value import VALUE\n\ndef test_value(): assert VALUE == 2\n',encoding='utf-8',newline='')
    items=[{'patch_item_id':'p1','path':'app/value.py','file_role':'production'}]
    if two: (root/'app/other.py').write_text('OTHER = 1\n',encoding='utf-8',newline=''); items.append({'patch_item_id':'p2','path':'app/other.py','file_role':'production'})
    paths=[x['path'] for x in items]; patch=art('patch','patch',ordered_patch_items=items); intake=art('intake','intake',session_id='s53',confirmed_paths=paths,repository_identity={'repository_id':'r53'})
    snapshots=snapshot_patch_sources(intake,patch,workspace_root=root)
    ops=[]
    for i,path in enumerate(paths,1):
        before='VALUE = 1\n' if i==1 else 'OTHER = 1\n'; after='VALUE = 2\n' if i==1 else 'OTHER = 2\n'
        ops.append({'operation_id':f'op-{i}','path':path,'operation_type':'replace_exact_text','source_sha256':sha(before),'expected_result_sha256':sha(after),'old_text':'1','new_text':'2','candidate_content':after,'depends_on':[],'scope_binding':'confirmed','acceptance_criteria':['fixed'],'verification_targets':['tests/test_value.py']})
    package=art('zero.engineering.governed_change_package.v1','change_package',session_id='s53',iteration_reference={'iteration':1},repository_identity={'repository_id':'r53'},workspace_snapshot_reference={},source_snapshot_references=[_ref(x) for x in snapshots['sources']],ordered_operations=ops,ordered_paths=paths,operation_count=len(ops),confirmed_scope=paths,verification_plan={'targets':['tests/test_value.py'],'bounded':True,'timeout_seconds':120},rollback_plan={'required':True},acceptance_criterion_mappings=['fixed'],package_status='candidate',execution_authority='not_granted',authority=AUTHORITY)
    approval=art('approval','approval',decision='approved',change_package_candidate_reference=_ref(package)); authorization=art('authorization','authorization',decision='authorized',change_package_reference=_ref(package)); authorized=art('authorized','authorized',change_package_reference=_ref(package),approval_reference=_ref(approval),authorization_reference=_ref(authorization),authorization_status='granted',replay_status='unused'); readiness=art('readiness','readiness',readiness_status='ready_for_explicit_apply')
    raw={'authorized_change_package_reference':_ref(authorized),'execution_readiness_reference':_ref(readiness),'human_actor':'alice','decision':'confirmed','confirmed_package_fingerprint':package['change_package_fingerprint'],'confirmed_operation_ids':[x['operation_id'] for x in ops],'confirmed_paths':paths,'confirmed_test_targets':['tests/test_value.py'],'workspace_snapshot_acknowledgement':True,'source_snapshot_acknowledgements':package['source_snapshot_references'],'rollback_acknowledgement':True}
    request=build_explicit_apply_request(authorized,readiness,approval,authorization,raw)
    return root,patch,intake,snapshots,package,approval,authorization,authorized,readiness,request

def admit(p,**changes):
    args=dict(source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0]); args.update(changes)
    return admit_patch_apply(p[9],p[7],p[8],p[4],p[5],p[6],**args)

def test_request_requires_human_and_exact_references(tmp_path):
    p=prepared(tmp_path)
    with pytest.raises(ExplicitPatchApplyError,match='missing_human_actor'): build_explicit_apply_request(p[7],p[8],p[5],p[6],{})
    bad={'human_actor':'a','decision':'confirmed','authorized_change_package_reference':{},'execution_readiness_reference':_ref(p[8])}
    with pytest.raises(ExplicitPatchApplyError,match='wrong_authorization_reference'): build_explicit_apply_request(p[7],p[8],p[5],p[6],bad)

def test_admission_is_read_only_and_exact(tmp_path):
    p=prepared(tmp_path); before=(p[0]/'app/value.py').read_bytes(); admission=admit(p)
    assert admission['admission_status']=='admitted' and not admission['mutation_performed'] and (p[0]/'app/value.py').read_bytes()==before

@pytest.mark.parametrize(('field','value','reason'),[('decision','rejected','apply_request_not_confirmed'),('confirmed_package_fingerprint','bad','wrong_package_fingerprint'),('confirmed_operation_ids',[],'operation_substitution'),('confirmed_paths',[],'path_substitution'),('confirmed_test_targets',[],'verification_target_not_authorized')])
def test_admission_fail_closed_request_mismatch(tmp_path,field,value,reason):
    p=prepared(tmp_path); request={**p[9],field:value}; result=admit_patch_apply(request,p[7],p[8],p[4],p[5],p[6],source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0]); assert reason in result['reason_codes']

def test_admission_blocks_replay_readiness_and_drift(tmp_path):
    p=prepared(tmp_path); result=admit_patch_apply(p[9],{**p[7],'replay_status':'used'},p[8],p[4],p[5],p[6],source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0]); assert 'authorization_replay' in result['reason_codes']
    (p[0]/'app/value.py').write_text('VALUE = 9\n',encoding='utf-8'); assert 'workspace_drift' in admit(p)['reason_codes']

def test_successful_apply_consumes_once_and_records_evidence(tmp_path):
    p=prepared(tmp_path); admission=admit(p); usage=reserve_authorization(admission,p[7],p[6]); tx,evidence,used,result=apply_authorized_patch(admission,usage,p[7],p[4],workspace_root=p[0])
    assert result['mutation_status']=='applied' and used['authorization_usage']=='consumed' and used['use_count']==1 and tx['transaction_status']=='committed'
    assert (p[0]/'app/value.py').read_text(encoding='utf-8')=='VALUE = 2\n' and evidence[0]['actual_post_sha256']==sha('VALUE = 2\n')
    with pytest.raises(ExplicitPatchApplyError,match='authorization_reserved_elsewhere'): apply_authorized_patch(admission,used,p[7],p[4],workspace_root=p[0])

def test_all_supported_operations(tmp_path):
    p=prepared(tmp_path); admission=admit(p); usage=reserve_authorization(admission,p[7],p[6])
    for typ,before,after,extra in [('replace_file_content','VALUE = 1\n','X\n',{}),('append_text','VALUE = 1\n','VALUE = 1\nX\n',{'append_text':'X\n'}),('remove_exact_text','VALUE = 1\n','VALUE = \n',{'old_text':'1'}),('create_text_file','', 'NEW\n',{})]:
        root=tmp_path/typ; root.mkdir(); path='new.py' if typ=='create_text_file' else 'f.py'
        if before: (root/path).write_text(before,encoding='utf-8',newline='')
        op={'operation_id':'one','path':path,'operation_type':typ,'source_sha256':sha(before) if before else None,'expected_result_sha256':sha(after),'candidate_content':after,**extra}; pkg={**p[4],'ordered_operations':[op],'ordered_paths':[path],'operation_count':1,'change_package_fingerprint':'fp'}; adm={**admission,'reserved_package_fingerprint':'fp','reserved_operation_ids':['one'],'reserved_paths':[path]}; use={**usage,'package_fingerprint':'fp','operation_ids':['one'],'authorization_usage':'reserved'}
        assert apply_authorized_patch(adm,use,p[7],pkg,workspace_root=root)[3]['mutation_status']=='applied'

def test_exact_match_and_hash_failure_do_not_leave_partial_mutation(tmp_path):
    p=prepared(tmp_path,two=True); package=copy.deepcopy(p[4]); package['ordered_operations'][1]['expected_result_sha256']='bad'; package=canon({k:v for k,v in package.items() if k not in {'change_package_fingerprint','change_package_id'}},'change_package_fingerprint','change_package_id','engineering-change_package-')
    admission=admit(p); admission={**admission,'reserved_package_fingerprint':package['change_package_fingerprint'],'reserved_operation_ids':['op-1','op-2'],'reserved_paths':package['ordered_paths']}; usage=reserve_authorization(admission,p[7],p[6]); result=apply_authorized_patch(admission,usage,p[7],package,workspace_root=p[0])[3]
    assert result['mutation_status']=='rolled_back' and (p[0]/'app/value.py').read_text(encoding='utf-8')=='VALUE = 1\n'

def test_focused_verification_and_completion_remain_human_gated(tmp_path):
    p=prepared(tmp_path); admission=admit(p); usage=reserve_authorization(admission,p[7],p[6]); _,evidence,_,result=apply_authorized_patch(admission,usage,p[7],p[4],workspace_root=p[0]); tests,verification=verify_applied_patch(result,p[4],workspace_root=p[0])
    assert verification['verification_status']=='passed' and tests[0]['status']=='passed'; candidate=build_completion_review_candidate(result,verification,evidence); assert candidate['completion_recommendation']=='eligible_for_human_completion_review'
    with pytest.raises(ExplicitPatchApplyError,match='missing_human_actor'): review_completion(candidate,{})
    review=review_completion(candidate,{'human_actor':'carol','decision':'completed','completion_candidate_reference':_ref(candidate)}); assert not review['commit_authority'] and not review['push_authority']

def test_failed_verification_does_not_retry_or_complete(tmp_path):
    p=prepared(tmp_path); (p[0]/'tests/test_value.py').write_text('def test_value(): assert False\n',encoding='utf-8'); admission=admit_patch_apply(p[9],p[7],p[8],p[4],p[5],p[6],source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0]); assert admission['admission_status']=='admitted'
    usage=reserve_authorization(admission,p[7],p[6]); _,evidence,_,result=apply_authorized_patch(admission,usage,p[7],p[4],workspace_root=p[0]); _,verification=verify_applied_patch(result,p[4],workspace_root=p[0]); candidate=build_completion_review_candidate(result,verification,evidence); assert not verification['completion_eligible'] and candidate['completion_recommendation']=='requires_repair_review'

def test_inspect_resume_store_and_cli(tmp_path):
    p=prepared(tmp_path); bundle={STORE_FILES['request']:p[9]}; assert resume_explicit_apply_state(bundle)['decision']=='requires_apply_admission'; assert not any(resume_explicit_apply_state(bundle)[x] for x in ('will_apply','will_retry','will_rollback','will_run_tests','will_complete','will_commit','will_push'))
    for path in STORE_FILES.values(): write_session_artifact(tmp_path,'s53',path,{'schema':'test'}); assert read_session_artifact(tmp_path,'s53',path)=={'schema':'test'}
    cp=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--help'],cwd=Path(__file__).parents[1],text=True,capture_output=True); assert cp.returncode==0
    for command in ('build-explicit-apply-request','confirm-explicit-apply','admit-patch-apply','apply-authorized-patch','verify-applied-patch','review-completion'): assert command in cp.stdout
    for forbidden in ('auto-apply','apply-latest','force-apply','create-pr'): assert forbidden not in cp.stdout
