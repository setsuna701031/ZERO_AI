import hashlib, json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_work_entry import create_engineering_work_request, admit_engineering_work, create_work_coordination, WorkEntryError
from core.engineering.engineering_read_only_pipeline import *


def make_repo(tmp_path):
    root=tmp_path/'repo'; (root/'docs').mkdir(parents=True); (root/'docs'/'guide.md').write_text('guide\n'); (root/'core').mkdir(); (root/'core'/'app.py').write_text('import json\n'); subprocess.run(['git','init'],cwd=root,capture_output=True); subprocess.run(['git','add','.'],cwd=root,capture_output=True); subprocess.run(['git','commit','-m','init'],cwd=root,capture_output=True); return root

def bundle(tmp_path, mode='governed_delivery', acceptance='verify docs updated'):
    root=make_repo(tmp_path); req=create_engineering_work_request(request_statement='prepare bounded docs change',repository_identity={'repository_id':'repo'},repository_root_reference='.',requested_scope=['docs'],excluded_scope=['.git'],acceptance_intent=acceptance,requested_mode=mode); intake=admit_engineering_work(req); coord=create_work_coordination(req,intake); pipe=create_read_only_pipeline(req,intake,coord); return root,req,intake,coord,pipe

def digest(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '.git' not in p.parts}

def test_deterministic_pipeline_creation_and_mutation_authority_not_granted(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path)
    assert pipe==create_read_only_pipeline(req,intake,coord)
    assert pipe['mutation_authority']=='not_granted' and pipe['requested_mode']=='governed_delivery'

def test_unsupported_requested_mode_and_duplicate_pipeline_rejection(tmp_path):
    root=make_repo(tmp_path)
    with pytest.raises(WorkEntryError): create_engineering_work_request(request_statement='x',repository_identity={'repository_id':'r'},repository_root_reference='.',requested_scope=['docs'],requested_mode='execute')
    root,req,intake,coord,pipe=bundle(tmp_path/'b')
    with pytest.raises(ReadOnlyPipelineError): create_read_only_pipeline(req,intake,coord,existing_pipeline=pipe)

def test_deterministic_stage_result_and_invalid_stage_enum(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path)
    ref=pipe['work_request_reference']; a=build_stage_result(pipeline=pipe,coordination=coord,stage='repository_admission',input_references=[ref],output_references=[ref])
    assert a==build_stage_result(pipeline=pipe,coordination=coord,stage='repository_admission',input_references=[ref],output_references=[ref])
    with pytest.raises(ReadOnlyPipelineError): build_stage_result(pipeline=pipe,coordination=coord,stage='execution',input_references=[ref],output_references=[ref])

def test_cross_session_output_and_completed_without_output_rejected(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path); bad={**pipe['work_request_reference'],'session_id':'other'}
    with pytest.raises(ReadOnlyPipelineError): build_stage_result(pipeline=pipe,coordination=coord,stage='repository_admission',input_references=[bad],output_references=[bad])
    with pytest.raises(ReadOnlyPipelineError): build_stage_result(pipeline=pipe,coordination=coord,stage='repository_admission',input_references=[pipe['work_request_reference']],output_references=[])

def test_governed_delivery_exact_stop_and_repository_unchanged(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path); before=digest(root); before_status=subprocess.run(['git','status','--short'],cwd=root,text=True,capture_output=True).stdout
    out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root)
    after=digest(root); after_status=subprocess.run(['git','status','--short'],cwd=root,text=True,capture_output=True).stdout
    assert out['pipeline']['pipeline_status']=='awaiting_human_approval'
    assert out['coordination']['current_stage']=='awaiting_approval'
    assert out['pipeline']['next_governed_action']=='requires_human_approval'
    assert out['artifacts']['human_gate_handoff']['approval_state']=='pending'
    assert out['artifacts']['human_gate_handoff']['authorization_state']=='not_granted'
    assert out['artifacts']['human_gate_handoff']['execution_state']=='not_started'
    assert before==after and before_status==after_status

def test_analysis_only_plan_only_proposal_only_exact_stops(tmp_path):
    expectations={'analysis_only':('completed_read_only_preparation','repository_analysis'),'plan_only':('completed_read_only_preparation','planning'),'proposal_only':('completed_read_only_preparation','proposal_review')}
    for mode, expected in expectations.items():
        root,req,intake,coord,pipe=bundle(tmp_path/mode,mode=mode)
        out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root)
        assert (out['pipeline']['pipeline_status'], out['pipeline']['current_stage'])==expected
        assert out['pipeline']['next_governed_action']=='requested_mode_complete'

def test_missing_acceptance_criteria_requires_input(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path, acceptance='human_review')
    out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root)
    assert out['pipeline']['pipeline_status']=='awaiting_input'
    assert out['pipeline']['next_governed_action']=='requires_acceptance_criteria'
    assert 'missing_acceptance_criteria' in out['pipeline']['missing_inputs']

def test_repository_admission_failure_blocks_analysis(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path)
    out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root/'missing')
    assert out['pipeline']['pipeline_status']=='blocked'
    assert out['pipeline']['next_governed_action']=='blocked'

def test_inspect_and_resume_are_read_only_and_legacy_not_initialized(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path); out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root); before=digest(root)
    ins=inspect_read_only_pipeline(out['coordination'],out['pipeline'],out['artifacts']); dec=resume_read_only_pipeline(out['coordination'],out['pipeline'])
    assert digest(root)==before
    assert ins['read_only_pipeline_status']=='awaiting_human_approval' and ins['timeline'][-1]['stage']=='Execution'
    assert dec['will_approve'] is False and dec['will_authorize'] is False and dec['will_execute'] is False and dec['will_mutate_repository'] is False
    assert inspect_read_only_pipeline(coord)['read_only_pipeline_status']=='not_initialized'

def test_verify_pipeline_corrupt_fails_closed(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path); out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root)
    assert verify_read_only_pipeline(out['pipeline'],out['stage_results'])['valid'] is True
    bad={**out['pipeline'],'pipeline_fingerprint':'bad'}
    assert verify_read_only_pipeline(bad)['valid'] is False

def test_journal_checkpoint_created(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path); out=run_read_only_pipeline(req,intake,coord,pipe,repository_root=root)
    assert out['journal']['events'][0]['event']=='read_only_pipeline_created'
    assert out['checkpoint']['current_stage']=='awaiting_approval'


def test_cli_submit_prepare_next_inspect_resume_verify_json(tmp_path):
    root,req,intake,coord,pipe=bundle(tmp_path)
    c=tmp_path/'c.json'; r=tmp_path/'r.json'; i=tmp_path/'i.json'; p=tmp_path/'p.json'
    for path,obj in [(c,coord),(r,req),(i,intake),(p,pipe)]: path.write_text(json.dumps(obj))
    for args in [
        ['submit','--statement','x','--repo-id','r','--repo-root','.','--scope','docs','--acceptance-intent','criteria'],
        ['prepare-next',str(c),'--request-json',str(r),'--intake-json',str(i),'--pipeline-json',str(p),'--repo-root',str(root)],
        ['inspect',str(c),'--pipeline-json',str(p)],
        ['resume',str(c),'--pipeline-json',str(p)],
        ['verify-pipeline',str(c),'--pipeline-json',str(p)],
    ]:
        run=subprocess.run([sys.executable,'-m','cli.zero_engineering_work',*args],text=True,capture_output=True)
        assert run.returncode==0, run.stderr+run.stdout
        json.loads(run.stdout)
