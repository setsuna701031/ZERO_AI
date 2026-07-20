from __future__ import annotations
import json, subprocess, sys, os, re
from pathlib import Path
from typing import Any, Mapping
from core.engineering.engineering_verification_plan_validation import validate_verification_plan
from core.engineering.engineering_verification_admission_validation import validate_verification_admission
from core.engineering.engineering_verification_admission import RUNNER_IDENTITY
from core.engineering.engineering_verification_run import build_verification_run, build_evidence_item
from core.engineering.engineering_completion_foundation import build_verification_result
SECRET_RE=re.compile(r'(?i)(secret|token|api[_-]?key|credential|password)=[^\s]+')
def _clean(s,limit):
 b=(s or '').encode('utf-8','replace'); raw=len(b); trunc=raw>limit; txt=b[:limit].decode('utf-8','replace'); txt=SECRET_RE.sub(r'\1=<redacted>',txt); return ' '.join(txt.split()),raw,len(txt.encode()),trunc
def _env():
 keep={k:os.environ[k] for k in ('SYSTEMROOT','TEMP','TMP') if k in os.environ}; keep.update({'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'}); return keep
def _targets(step): return list(step.get('target_reference') if isinstance(step.get('target_reference'),list) else [step.get('target_reference')])
def _run_proc(argv,cwd,timeout,limit):
 try:
  p=subprocess.run(argv,cwd=str(cwd),env=_env(),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=timeout,shell=False)
  out,ob,sb,to=_clean(p.stdout,limit); err,ob2,sb2,to2=_clean(p.stderr,limit); return ('passed' if p.returncode==0 else 'failed'),p.returncode,out,err,ob+ob2,sb+sb2,to or to2,[]
 except subprocess.TimeoutExpired as exc:
  out,ob,sb,to=_clean(exc.stdout if isinstance(exc.stdout,str) else '',limit); err,ob2,sb2,to2=_clean(exc.stderr if isinstance(exc.stderr,str) else 'timeout',limit); return 'timed_out',None,out,err,ob+ob2,sb+sb2,True,['timeout']
 except Exception as exc:
  return 'runner_error',None,'',str(exc)[:limit],0,0,False,['runner_error']
def run_governed_verification(*, repository_root:str|Path, session:Mapping[str,Any], proposal:Mapping[str,Any], repair_plan:Mapping[str,Any], execution_result:Mapping[str,Any], verification_plan:Mapping[str,Any], verification_admission:Mapping[str,Any], replay_state:Mapping[str,Any]|None=None)->dict[str,Any]:
 if replay_state and replay_state.get('verification_run') and replay_state.get('verification_result'):
  run=dict(replay_state['verification_run']); run['replay_count']=int(run.get('replay_count',0))+1; return {'replayed':True,'verification_run':run,'verification_result':dict(replay_state['verification_result']),'evidence':list(replay_state.get('evidence',[]))}
 pr=validate_verification_plan(verification_plan); ar=validate_verification_admission(verification_admission,verification_plan)
 if not pr.valid or not ar.valid or verification_admission.get('consumed') is True or verification_admission.get('admission_status')!='admitted': raise ValueError('verification_not_admitted:'+','.join(pr.errors+ar.errors))
 if session.get('current_stage')!='awaiting_verification': raise ValueError('session_not_awaiting_verification')
 root=Path(repository_root).resolve(); results=[]; evidence=[]; limit=int(verification_plan.get('maximum_output_bytes') or 4096); truncated=False
 for step in verification_plan.get('verification_steps') or []:
  vt=step['verification_type']; targets=_targets(step); status='blocked'; code=None; out=''; err=''; reasons=[]; ob=sb=0
  paths=[(root/t).resolve() for t in targets]
  if any(not str(p).startswith(str(root)) for p in paths): status='invalid'; reasons=['path_escape']
  elif vt=='pytest_files':
   if any((not p.is_file()) or p.suffix!='.py' for p in paths): status='invalid'; reasons=['invalid_pytest_file']
   else: status,code,out,err,ob,sb,tr,reasons=_run_proc([sys.executable,'-m','pytest','-q',*targets],root,int(step.get('timeout_seconds')),limit); truncated|=tr
  elif vt=='python_compile_files':
   if any((not p.is_file()) or p.suffix!='.py' for p in paths): status='invalid'; reasons=['invalid_python_file']
   else: status,code,out,err,ob,sb,tr,reasons=_run_proc([sys.executable,'-m','py_compile',*targets],root,int(step.get('timeout_seconds')),limit); truncated|=tr
  elif vt=='static_pattern_inspection':
   deny=step.get('arguments',{}).get('denylist') or ['shell=True','os.system(','eval(','exec(','pickle']
   hits=[]
   for p,t in zip(paths,targets):
    text=p.read_text(encoding='utf-8',errors='replace')[:limit] if p.is_file() else ''
    hits += [f'{t}:{d}' for d in deny if d in text]
   status='failed' if hits else 'passed'; out='; '.join(hits)[:limit]; code=1 if hits else 0
  elif vt in {'file_exists','file_not_exists'}:
   ok=all(p.is_file() for p in paths); status='passed' if (ok if vt=='file_exists' else not ok) else 'failed'; code=0 if status=='passed' else 1
  elif vt=='json_parse':
   try:
    for p in paths: json.loads(p.read_text(encoding='utf-8'))
    status='passed'; code=0
   except Exception as exc: status='failed'; code=1; err=str(exc)[:limit]
  else: status='blocked'; reasons=['unsupported_executor']
  ev=build_evidence_item(verification_run_id='pending',step_id=step['step_id'],evidence_type=vt,status=status,target_references=targets,exit_code=code,stdout_summary=out,stderr_summary=err,reason_codes=reasons,original_byte_count=ob,saved_byte_count=sb,output_truncated=truncated)
  sr={'step_id':step['step_id'],'verification_type':vt,'status':status,'exit_code':code,'duration_milliseconds':0,'stdout_summary':out,'stderr_summary':err,'evidence_reference':ev['evidence_id'],'reason_codes':reasons}
  evidence.append(ev); results.append(sr)
  if verification_plan.get('fail_fast') and step.get('mandatory') and status!='passed': break
 run_status='passed' if all((not s.get('mandatory')) or r['status']=='passed' for s,r in zip(verification_plan.get('verification_steps') or [],results)) else ('runner_error' if any(r['status']=='runner_error' for r in results) else 'blocked' if any(r['status'] in {'blocked','timed_out','invalid'} for r in results) else 'failed')
 run=build_verification_run(plan=verification_plan,admission=verification_admission,step_results=results,evidence_references=[{'evidence_id':e['evidence_id'],'fingerprint':e['fingerprint']} for e in evidence],run_status=run_status,output_truncated=truncated)
 exp_results=[]
 for step,r in zip(verification_plan.get('verification_steps') or [],results): exp_results.append({'expectation_id':step.get('expectation_id'),'expectation_type':step.get('verification_type'),'status':'passed' if r['status']=='passed' else ('failed' if r['status']=='failed' else 'blocked'),'summary':r['status'],'evidence_reference_ids':[r['evidence_reference']]})
 vstatus='passed' if run_status=='passed' else ('failed' if run_status=='failed' else 'blocked')
 vr=build_verification_result(task_id=verification_plan.get('task_id'),repository_identity=verification_plan.get('repository_identity'),proposal=proposal,repair_plan=repair_plan,execution_result=execution_result,verification_status=vstatus,verification_expectation_results=exp_results,evidence_references=[{'evidence_id':e['evidence_id'],'fingerprint':e['fingerprint']} for e in evidence],verified_target_paths=verification_plan.get('allowed_target_paths'))
 adm=dict(verification_admission); adm['consumed']=True; adm['admission_status']=adm['status']='consumed'
 return {'replayed':False,'verification_run':run,'verification_result':vr,'verification_admission':adm,'evidence':evidence}
