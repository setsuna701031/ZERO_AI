import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_multifile_coding_workflow import build_multifile_change_plan_candidate, inspect_multifile_state, resume_multifile_state, validate_multifile_change_plan_candidate
from core.engineering.engineering_natural_language_intake import STORE_FILES, NaturalLanguageIntakeError, confirm_specification, create_formal_work_request_from_confirmed_specification, load_intake_bundle, persist_formalized, start_natural_language_intake
from core.engineering.engineering_runtime_session_store import load_session_store, write_session_artifact


def ref(value, identity, fingerprint):
    return {'schema':value['schema'],'artifact_identity':value[identity],'artifact_fingerprint':value[fingerprint],'session_id':value.get('session_id')}


def governed(tmp_path):
    repo=tmp_path/'repo'; (repo/'docs').mkdir(parents=True); (repo/'docs/usage.md').write_text('usage\n',encoding='utf-8')
    store=tmp_path/'sessions'; started=start_natural_language_intake('update docs/usage.md documentation',store_root=store,repository=repo,repo_id='repo-v42')
    candidate=started['specification_candidate']; raw={'specification_candidate_reference':ref(candidate,'specification_candidate_id','specification_candidate_fingerprint'),'human_actor':'alice','decision':'confirm','confirmed_scope':candidate['included_paths'],'confirmed_acceptance_criteria':candidate['acceptance_criteria'],'confirmed_constraints':['docs only'],'risk_acknowledgement':True}
    confirmation=confirm_specification(candidate,raw); sid=started['natural_language_intake']['intake_id']; write_session_artifact(store,sid,STORE_FILES['confirmation'],confirmation)
    identity={'repository_id':'repo-v42',**started['repository_evidence']['repository_identity']}
    formalized=create_formal_work_request_from_confirmed_specification(candidate,confirmation,repository_identity=identity)
    persist_formalized(store,sid,formalized); bundle=load_session_store(store,sid)
    plan=build_multifile_change_plan_candidate(confirmed_specification=confirmation,work_request=bundle['work-entry/request.json'],repository_analysis=bundle[STORE_FILES['evidence']],repository_identity=identity,session_id=sid)
    return store,sid,bundle,candidate,confirmation,formalized['work_request'],plan


def validate(parts, plan=None, **overrides):
    _,sid,bundle,_,confirmation,request,built=parts
    args={'confirmed_specification':confirmation,'work_request':request,'repository_analysis':bundle[STORE_FILES['evidence']],'session_id':sid}; args.update(overrides)
    return validate_multifile_change_plan_candidate(plan or built,**args)


def test_confirmed_specification_formalizes_existing_contract_and_linkage(tmp_path):
    parts=governed(tmp_path); _,_,_,candidate,confirmation,request,plan=parts
    assert request['schema']=='zero.engineering.work_request.v1'
    assert request['source_actor_reference']['specification_decision_reference']==ref(confirmation,'confirmation_id','confirmation_fingerprint')
    assert request['source_actor_reference']['natural_language_lineage']==candidate['intake_reference']
    assert request['repository_identity']['repository_root_fingerprint']
    assert plan['work_request_reference'] and plan['confirmed_specification_reference'] and plan['repository_analysis_reference']
    result=validate(parts); assert result['valid'], result


def test_unconfirmed_missing_actor_scope_and_incomplete_rejected(tmp_path):
    started=start_natural_language_intake('update README.md documentation',store_root=tmp_path/'s',repository=Path.cwd())
    candidate=started['specification_candidate']
    with pytest.raises(NaturalLanguageIntakeError): create_formal_work_request_from_confirmed_specification(candidate,{'confirmation_status':'rejected'})
    with pytest.raises(NaturalLanguageIntakeError): create_formal_work_request_from_confirmed_specification(candidate,{'confirmation_status':'confirmed'})


@pytest.mark.parametrize(('mutation','reason'),[
    ('work_fingerprint','wrong_work_request_fingerprint'),('spec_reference','wrong_specification_reference'),('repository_identity','wrong_repository_identity'),('scope','scope_mismatch'),('session','plan_created_from_different_session'),('preconfirmation','work_request_created_before_human_confirmation'),('path_expansion','unapproved_scope_expansion')])
def test_fail_closed_linkage_cases(tmp_path,mutation,reason):
    parts=governed(tmp_path); _,_,_,_,confirmation,request,plan=parts; plan=copy.deepcopy(plan); kwargs={}
    if mutation=='work_fingerprint': plan['work_request_reference']['artifact_fingerprint']='wrong'
    elif mutation=='spec_reference': plan['confirmed_specification_reference']['artifact_fingerprint']='wrong'
    elif mutation=='repository_identity': plan['repository_identity']={'repository_id':'other'}
    elif mutation=='scope': request=copy.deepcopy(request); request['requested_scope']=['other/path.py']; kwargs['work_request']=request
    elif mutation=='session': plan['session_id']='other-session'
    elif mutation=='preconfirmation': request=copy.deepcopy(request); request['source_actor_reference']['specification_decision_reference']={'artifact_identity':'old','artifact_fingerprint':'old'}; kwargs['work_request']=request
    elif mutation=='path_expansion': plan['ordered_file_changes'][0]['path']='outside/path.py'
    assert reason in validate(parts,plan,**kwargs)['errors']


def test_unconfirmed_and_stale_work_request_rejected(tmp_path):
    parts=governed(tmp_path); confirmation=copy.deepcopy(parts[4]); confirmation['confirmation_status']='rejected'
    assert 'unconfirmed_specification' in validate(parts,confirmed_specification=confirmation)['errors']
    stale=copy.deepcopy(parts[5]); stale['source_actor_reference']['specification_decision_reference']['artifact_fingerprint']='stale'
    assert 'stale_work_request' in validate(parts,work_request=stale)['errors']


def test_legacy_inspect_incomplete_and_resume_read_only(tmp_path):
    before=dict(load_session_store(tmp_path,'legacy')) if (tmp_path/'legacy').exists() else {}
    bundle={'work-entry/specification-candidate.json':{'candidate_status':'ready_for_confirmation'}}
    assert inspect_multifile_state(bundle)['multifile_coding_workflow_status']=='incomplete'
    assert resume_multifile_state(bundle)['decision']=='requires_multifile_plan'
    assert before==({} if not (tmp_path/'legacy').exists() else load_session_store(tmp_path,'legacy'))


def test_cli_end_to_end_stops_at_human_plan_confirmation(tmp_path):
    store,sid,bundle,_,_,_,_=governed(tmp_path)
    root=Path(__file__).parents[1]; base=[sys.executable,'cli/zero_engineering_work.py','--format','json','--store-root',str(store),'--session-id',sid]
    built=subprocess.run(base+['build-multifile-plan'],cwd=root,text=True,capture_output=True); assert built.returncode==0, built.stdout+built.stderr
    checked=subprocess.run(base+['validate-multifile-plan'],cwd=root,text=True,capture_output=True); assert checked.returncode==0
    result=json.loads(checked.stdout); assert result['valid'], result
    inspected=json.loads(subprocess.run(base+['inspect'],cwd=root,text=True,capture_output=True,check=True).stdout)
    assert inspected['formal_work_request_status']=='created' and inspected['multifile_plan_validation_status']=='valid'
    resumed=json.loads(subprocess.run(base+['resume'],cwd=root,text=True,capture_output=True,check=True).stdout)
    assert resumed['decision']=='requires_plan_confirmation'
    assert all(resumed[k] is False for k in ('will_modify_repository','will_execute_tests','will_approve','will_authorize','will_retry','will_complete'))


def test_authority_boundary_and_work_request_contract_unchanged(tmp_path):
    parts=governed(tmp_path); request=parts[5]; plan=parts[-1]
    assert plan['authority']=={'may_approve':False,'may_authorize':False,'may_execute':False,'may_complete':False}
    assert request['schema']=='zero.engineering.work_request.v1'
