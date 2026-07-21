from __future__ import annotations
import os, shutil, subprocess, sys, time
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import canonical_json, fingerprint
from core.engineering.engineering_approval_execution_activation import ActivationError

CHANGE_PACKAGE_SCHEMA="zero.engineering.governed_change_package.v1"
TEST_POLICY_SCHEMA="zero.engineering.bounded_test_policy.v1"
EVIDENCE_SCHEMA="zero.engineering.practical_execution_evidence.v1"
VERIFY_SCHEMA="zero.engineering.practical_verification.v1"
ALLOWED_OPS={"create_text_file","replace_text_exact","append_text","remove_text_exact","rename_file","create_directory","run_bounded_test"}
MUTATION_OPS=ALLOWED_OPS-{"run_bounded_test"}
PROHIBITED_TOKENS={"|",">","&&",";","bash","-c","cmd","/c","python"+" -c","shell"+"=True","powershell"}
MAX_TEXT=1_000_000

def _canon(body:Mapping[str,Any], fp_key:str, id_key:str, prefix:str)->dict[str,Any]:
    b=dict(body); fp=fingerprint(b); b[fp_key]=fp; b[id_key]=prefix+fp[:24]; return b

def sha_text(text:str)->str: return fingerprint(text.encode('utf-8').hex())
def sha_file(path:Path)->str: return fingerprint(path.read_bytes().hex())

def safe_path(root: str|Path, rel: str, *, allow_missing: bool=True)->Path:
    s=str(rel).replace('\\','/').strip()
    if not s or s.startswith('/') or s in {'.','*'} or '..' in s.split('/') or s.startswith('.git/') or s=='.git' or '\x00' in s:
        raise ActivationError('unsafe_path_rejection')
    p=(Path(root).resolve()/s).resolve(strict=False)
    if not str(p).startswith(str(Path(root).resolve())+os.sep) and p != Path(root).resolve():
        raise ActivationError('workspace_escape_rejected')
    if p.exists() and p.is_symlink():
        raise ActivationError('symlink_escape_rejected')
    if p.exists() and p.is_file():
        try: p.read_text(encoding='utf-8')
        except UnicodeDecodeError: raise ActivationError('binary_file_rejected')
    if not allow_missing and not p.exists(): raise ActivationError('missing_path')
    return p

def bounded_test_policy(**overrides:Any)->dict[str,Any]:
    body={"schema":TEST_POLICY_SCHEMA,"allowed_runner":sys.executable,"allowed_module":"pytest","allowed_flags":["-q","--maxfail=1","-x","-k"],"allowed_test_roots":["tests"],"prohibited_tokens":sorted(PROHIBITED_TOKENS),"default_timeout_seconds":120,"maximum_timeout_seconds":120,"maximum_targets":3,"maximum_output_bytes":12000,"network_policy":"prohibited","environment_policy":"bounded","shell":False}
    body.update(overrides); return _canon(body,'test_policy_fingerprint','test_policy_id','engineering-bounded-test-policy-')

def _op_paths(op:Mapping[str,Any])->list[str]:
    if op.get('operation_type')=='rename_file': return [op.get('source_path',''), op.get('target_path','')]
    return [op.get('target_path','')]

def build_governed_change_package(*, confirmed_specification:Mapping[str,Any]|None, work_request:Mapping[str,Any]|None, read_only_analysis:Mapping[str,Any]|None=None, proposal:Mapping[str,Any]|None=None, operation_plan:Sequence[Mapping[str,Any]]|None=None, repository_identity:Mapping[str,Any]|None=None, workspace_root:str='.', approval:Mapping[str,Any]|None=None, authorization:Mapping[str,Any]|None=None, expected_unchanged_paths:Sequence[str]=(), risk_level:str='medium')->dict[str,Any]:
    if not confirmed_specification: raise ActivationError('confirmed_specification_required')
    if not work_request: raise ActivationError('work_request_required')
    ops=[dict(o) for o in (operation_plan or [])]
    if not ops: raise ActivationError('manual_operation_definition_required')
    scope=list(confirmed_specification.get('confirmed_scope') or work_request.get('requested_scope') or [])
    for i,o in enumerate(ops):
        o.setdefault('operation_id',f'op-{i+1:04d}'); o.setdefault('encoding','utf-8'); o.setdefault('before_state',{}); o.setdefault('constraints',{}); o.setdefault('operation_status','planned')
    changed=sorted({p for o in ops if o.get('operation_type') in MUTATION_OPS for p in _op_paths(o) if p})
    body={"schema":CHANGE_PACKAGE_SCHEMA,"work_request_reference":_ref(work_request),"confirmed_specification_reference":_ref(confirmed_specification),"read_only_analysis_reference":_ref(read_only_analysis or {}),"proposal_reference":_ref(proposal or {}),"approval_reference":_ref(approval or {}) if approval else None,"authorization_scope_reference":_ref(authorization or {}) if authorization else None,"repository_identity":dict(repository_identity or work_request.get('repository_identity') or {}),"workspace_root":workspace_root,"package_status":"draft","ordered_operations":ops,"expected_changed_paths":changed,"expected_unchanged_paths":list(expected_unchanged_paths),"validation_plan":{"requires_before_state":True,"requires_scope_match":True},"test_plan":{"required":any(o.get('operation_type')=='run_bounded_test' for o in ops)},"risk_level":risk_level,"blocked_reasons":[],"confirmed_scope":scope}
    return _canon(body,'change_package_fingerprint','change_package_id','engineering-governed-change-package-')

def _ref(a:Mapping[str,Any])->dict[str,Any]:
    return {k:v for k,v in a.items() if k=='schema' or k.endswith('_id') or k.endswith('_fingerprint') or k=='fingerprint'}

def validate_governed_change_package(pkg:Mapping[str,Any], *, workspace_root:str|Path|None=None, approval:Mapping[str,Any]|None=None, authorization:Mapping[str,Any]|None=None, policy:Mapping[str,Any]|None=None)->dict[str,Any]:
    errors=[]
    try:
        if pkg.get('schema')!=CHANGE_PACKAGE_SCHEMA: errors.append('schema_invalid')
        expected=_canon({k:v for k,v in pkg.items() if k not in {'change_package_fingerprint','change_package_id'}},'change_package_fingerprint','change_package_id','engineering-governed-change-package-')
        if expected.get('change_package_fingerprint')!=pkg.get('change_package_fingerprint'): errors.append('fingerprint_mismatch')
        ops=pkg.get('ordered_operations') or []
        if not ops: errors.append('empty_package_rejected')
        ids=[o.get('operation_id') for o in ops]
        if len(ids)!=len(set(ids)): errors.append('duplicate_operation_id_rejected')
        seen={}
        root=Path(workspace_root or pkg.get('workspace_root') or '.')
        scope=pkg.get('confirmed_scope') or []
        changed=sorted({p for o in ops if o.get('operation_type') in MUTATION_OPS for p in _op_paths(o) if p})
        if changed!=sorted(pkg.get('expected_changed_paths') or []): errors.append('expected_changed_paths_mismatch')
        pol=policy or bounded_test_policy()
        for o in ops:
            typ=o.get('operation_type')
            if typ not in ALLOWED_OPS: errors.append('unsupported_operation_rejected'); continue
            for rel in _op_paths(o):
                try: safe_path(root,rel)
                except ActivationError as e: errors.append(e.code)
                if rel and scope and not any(rel==s or rel.startswith(s.rstrip('/')+'/') for s in scope): errors.append('mutation_outside_scope')
            tgt=o.get('target_path')
            if typ in MUTATION_OPS and tgt in seen and seen[tgt]!=typ: errors.append('conflicting_target_operations_rejected')
            seen[tgt]=typ
            if typ in {'replace_text_exact','append_text','remove_text_exact','rename_file'} and not (o.get('before_state') or {}).get('sha256') and not o.get('expected_before_hash'): errors.append('missing_before_hash')
            if typ=='create_text_file' and safe_path(root,tgt).exists(): errors.append('create_over_existing_file')
            if typ=='run_bounded_test': errors += _validate_test_op(o, root, pol)
        if approval and approval.get('package_fingerprint') not in {None,pkg.get('change_package_fingerprint')}: errors.append('package_changed_after_approval_rejected')
        if authorization and authorization.get('package_fingerprint') not in {None,pkg.get('change_package_fingerprint')}: errors.append('authorization_package_mismatch')
    except ActivationError as e: errors.append(e.code)
    return {'valid':not errors,'errors':sorted(set(errors)),'package_validation_status':'valid' if not errors else 'invalid'}

def _validate_test_op(o:Mapping[str,Any], root:Path, policy:Mapping[str,Any])->list[str]:
    errors=[]; targets=o.get('test_targets') or ([o.get('target_path')] if o.get('target_path') else [])
    if not targets: return ['full_suite_rejected']
    if len(targets)>policy.get('maximum_targets',3): errors.append('unbounded_test')
    flags=o.get('flags') or ['-q']
    for f in flags:
        if f not in policy.get('allowed_flags',[]): errors.append('unsupported_test_flag')
        if any(t in str(f) for t in PROHIBITED_TOKENS): errors.append('prohibited_test_token')
    for t in targets:
        if any(x in str(t) for x in PROHIBITED_TOKENS): errors.append('prohibited_test_token')
        rel=str(t).split('::')[0]
        try: safe_path(root, rel)
        except ActivationError as e: errors.append(e.code)
        roots=policy.get('allowed_test_roots') or ['tests']
        if not any(rel==r or rel.startswith(r.rstrip('/')+'/') for r in roots): errors.append('test_outside_root_rejected')
    if int(o.get('timeout_seconds') or policy.get('default_timeout_seconds',120))>policy.get('maximum_timeout_seconds',120): errors.append('unbounded_test')
    return errors

def preview_practical_execution(pkg:Mapping[str,Any], **kw:Any)->dict[str,Any]:
    v=validate_governed_change_package(pkg, **kw)
    return {'schema':'zero.engineering.practical_preview.v1','change_package_id':pkg.get('change_package_id'),'change_package_fingerprint':pkg.get('change_package_fingerprint'),'ordered_operations':[{k:o.get(k) for k in ('operation_id','operation_type','target_path','source_path','before_state','expected_occurrence_count','timeout_seconds','test_targets')} for o in pkg.get('ordered_operations',[])],'expected_changed_paths':pkg.get('expected_changed_paths',[]),'expected_unchanged_paths':pkg.get('expected_unchanged_paths',[]),'workspace_drift_status':'not_checked' if v['valid'] else 'blocked','blocking_reasons':v['errors'],'authorization_consumption_state':'unconsumed','mutation_occurred':False,'tests_executed':False}

def execute_practical_change_package(pkg:Mapping[str,Any], *, approval:Mapping[str,Any], authorization:Mapping[str,Any], admitted:bool, confirm_execution:bool, workspace_root:str|Path='.', policy:Mapping[str,Any]|None=None, run_tests:bool=True)->dict[str,Any]:
    if not confirm_execution: return {'execution_status':'execution_confirmation_required','mutation_occurred':False,'authorization_consumed':False}
    if approval.get('decision')!='approved': return _blocked('approval_required')
    if not authorization or authorization.get('consumption_state','unconsumed')!='unconsumed': return _blocked('authorization_reuse_rejected')
    if not admitted: return _blocked('adapter_admission_required')
    if authorization.get('package_fingerprint') not in {None,pkg.get('change_package_fingerprint')}: return _blocked('authorization_package_mismatch')
    root=Path(workspace_root); policy=policy or bounded_test_policy(); pre=validate_governed_change_package(pkg,workspace_root=root,approval=approval,authorization=authorization,policy=policy)
    if not pre['valid']: return _blocked(pre['errors'][0])
    before={}; backups={}; results=[]; created=[]; modified=[]; renamed=[]; rollback={'attempted':False,'status':'not_required'}
    try:
        for o in pkg['ordered_operations']:
            if o['operation_type'] in MUTATION_OPS:
                _prevalidate_op(o, root, authorization)
                key=o.get('source_path') if o.get('operation_type')=='rename_file' else o.get('target_path')
                p=safe_path(root,key)
                before[str(key)]=sha_file(p) if p.exists() and p.is_file() else None
        for o in pkg['ordered_operations']:
            if o['operation_type']=='run_bounded_test': continue
            r=_apply_op(o, root, backups); results.append(r)
            if r['status'] not in {'succeeded','already_exists'}: raise ActivationError(r['status'])
            if r['mutation_occurred']:
                if o['operation_type']=='create_text_file': created.append(o['target_path'])
                elif o['operation_type']=='rename_file': renamed.append({'source_path':o['source_path'],'target_path':o['target_path'],'content_hash_preserved':r['before_hash']==r['after_hash']})
                else: modified.append(o['target_path'])
    except Exception as e:
        rollback=_rollback(root, backups); return {'schema':EVIDENCE_SCHEMA,'execution_status':'failed','failure_classification':str(getattr(e,'code',e)),'mutation_occurred':False,'authorization_consumed':False,'operation_results':results,'rollback_status':rollback,'evidence_status':'failed'}
    tests=[run_bounded_test_operation(o, root, policy) for o in pkg['ordered_operations'] if o['operation_type']=='run_bounded_test'] if run_tests else []
    after={p:sha_file(root/p) for p in created+modified+[x['target_path'] for x in renamed] if (root/p).exists() and (root/p).is_file()}
    test_paths=[t for o in pkg.get('ordered_operations',[]) if o.get('operation_type')=='run_bounded_test' for t in (o.get('test_targets') or [o.get('target_path')]) if t]
    diff=git_diff_evidence(root, list(pkg.get('expected_changed_paths',[]))+test_paths)
    return _canon({'schema':EVIDENCE_SCHEMA,'execution_reference':{'controlled_execution_reused':'v3.7 explicit activation boundary'},'change_package_reference':_ref(pkg),'authorization_reference':_ref(authorization),'workspace_before_fingerprint':fingerprint(before),'workspace_after_fingerprint':fingerprint(after),'operation_results':results,'created_paths':created,'modified_paths':modified,'renamed_paths':renamed,'unchanged_protected_paths':pkg.get('expected_unchanged_paths',[]),'before_hashes':before,'after_hashes':after,'rollback_status':rollback,'test_results':tests,'git_diff_summary':diff,'unexpected_changes':diff.get('unexpected_paths',[]),'evidence_status':'collected','execution_status':'executed','mutation_occurred':bool(created or modified or renamed),'authorization_consumed':True,'authorization_consumption_count':1},'evidence_fingerprint','evidence_id','engineering-practical-execution-evidence-')

def _blocked(code): return {'execution_status':code,'mutation_occurred':False,'authorization_consumed':False,'operation_results':[],'evidence_status':'blocked'}
def _prevalidate_op(o, root, auth):
    paths=_op_paths(o); scope=auth.get('authorized_scope') or []
    for rel in paths:
        safe_path(root,rel)
        if scope and not any(rel==s or rel.startswith(s.rstrip('/')+'/') for s in scope): raise ActivationError('authorization_scope_mismatch')
    typ=o['operation_type']; p=safe_path(root,o.get('source_path') if typ=='rename_file' else o.get('target_path'))
    if typ!='create_text_file' and typ!='create_directory' and not p.exists(): raise ActivationError('workspace_drift_detected')
    if p.exists() and p.is_dir() and typ not in {'create_directory','rename_file'}: raise ActivationError('directory_target_rejected')
    before=(o.get('before_state') or {}).get('sha256') or o.get('expected_before_hash')
    if before and p.exists() and p.is_file() and sha_file(p)!=before: raise ActivationError('workspace_drift_detected')
    if typ in {'replace_text_exact','remove_text_exact'}:
        txt=p.read_text(encoding='utf-8'); old=o.get('old_text') or o.get('content') or ''
        if txt.count(old)!=int(o.get('expected_occurrence_count',1)): raise ActivationError('operation_mismatch')

def _apply_op(o, root, backups):
    typ=o['operation_type']; target=safe_path(root,o.get('source_path') if typ=='rename_file' else o.get('target_path',''))
    before_hash=sha_file(target) if target.exists() and target.is_file() else None; bytes_before=target.stat().st_size if target.exists() and target.is_file() else 0
    if target.exists(): backups.setdefault(o.get('target_path'), target.read_bytes() if target.is_file() else b'__DIR__')
    if typ=='create_directory':
        if target.exists(): return _res(o,'already_exists',False,before_hash,before_hash,bytes_before,bytes_before)
        target.mkdir(); return _res(o,'succeeded',True,None,None,0,0)
    if typ=='create_text_file':
        if target.exists(): return _res(o,'create_existing_file_rejected',False,before_hash,before_hash,bytes_before,bytes_before)
        target.parent.mkdir(parents=False, exist_ok=True); content=str(o.get('content',''))
        if len(content.encode('utf-8'))>MAX_TEXT: return _res(o,'content_too_large',False,None,None,0,0)
        target.write_text(content,encoding='utf-8',newline=''); ah=sha_file(target); return _res(o,'succeeded',True,None,ah,0,target.stat().st_size)
    txt=target.read_text(encoding='utf-8')
    if typ=='replace_text_exact': new=txt.replace(o.get('old_text',''),o.get('new_text',''),int(o.get('expected_occurrence_count',1)))
    elif typ=='append_text':
        app=o.get('append_content','');
        if txt.endswith(app): return _res(o,'replay_rejected',False,before_hash,before_hash,bytes_before,bytes_before)
        new=txt+app
    elif typ=='remove_text_exact':
        old=o.get('old_text') or o.get('content') or ''; new=txt.replace(old,'',int(o.get('expected_occurrence_count',1)))
        if not new and not o.get('constraints',{}).get('allow_empty_file'): return _res(o,'empty_file_rejected',False,before_hash,before_hash,bytes_before,bytes_before)
    elif typ=='rename_file':
        src=safe_path(root,o['source_path']); dst=safe_path(root,o['target_path']);
        if src.is_dir(): return _res(o,'rename_directory_rejected',False,before_hash,before_hash,bytes_before,bytes_before)
        if dst.exists(): return _res(o,'rename_existing_target_rejected',False,before_hash,before_hash,bytes_before,bytes_before)
        backups.setdefault(o['source_path'],src.read_bytes()); shutil.move(str(src),str(dst)); return _res(o,'succeeded',True,before_hash,sha_file(dst),bytes_before,dst.stat().st_size)
    target.write_text(new,encoding='utf-8',newline=''); ah=sha_file(target)
    if o.get('expected_after_hash') and ah!=o['expected_after_hash']: return _res(o,'after_hash_mismatch',False,before_hash,ah,bytes_before,target.stat().st_size)
    return _res(o,'succeeded',True,before_hash,ah,bytes_before,target.stat().st_size)

def _res(o,status,mut,bh,ah,bb,ba): return {'operation_id':o.get('operation_id'),'operation_type':o.get('operation_type'),'target_path':o.get('target_path'),'status':status,'mutation_occurred':mut,'before_hash':bh,'after_hash':ah,'bytes_before':bb,'bytes_after':ba,'details':{}}
def _rollback(root, backups):
    for rel,data in backups.items():
        p=safe_path(root,rel); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
    return {'attempted':bool(backups),'status':'rolled_back' if backups else 'not_required','manual_recovery_required':False}

def run_bounded_test_operation(o:Mapping[str,Any], root:Path, policy:Mapping[str,Any]|None=None)->dict[str,Any]:
    policy=policy or bounded_test_policy(); errors=_validate_test_op(o,root,policy)
    if errors: return {'runner':'pytest','status':'rejected','errors':errors,'mutation_occurred':False}
    targets=o.get('test_targets') or [o['target_path']]; flags=o.get('flags') or ['-q']; cmd=[policy['allowed_runner'],'-m',policy['allowed_module'],*targets,*flags]
    start=time.monotonic(); timed=False
    try: cp=subprocess.run(cmd,cwd=str(root),text=True,capture_output=True,timeout=int(o.get('timeout_seconds') or policy['default_timeout_seconds']),env={'PYTHONPATH':str(root),'PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired as e: cp=None; timed=True; out=(e.stdout or '')[:policy['maximum_output_bytes']]; err=(e.stderr or '')[:policy['maximum_output_bytes']]
    dur=time.monotonic()-start
    if cp is not None: out=cp.stdout[:policy['maximum_output_bytes']]; err=cp.stderr[:policy['maximum_output_bytes']]
    return {'runner':'pytest','working_directory':str(root),'test_targets':targets,'timeout_seconds':int(o.get('timeout_seconds') or policy['default_timeout_seconds']),'environment_allowlist':['PYTHONPATH'],'expected_exit_codes':o.get('expected_exit_codes',[0]),'maximum_output_bytes':policy['maximum_output_bytes'],'command_tokens':cmd,'exit_code':None if timed else cp.returncode,'duration_seconds':round(dur,3),'stdout_summary':out,'stderr_summary':err,'timed_out':timed,'status':'timed_out' if timed else ('passed' if cp.returncode in o.get('expected_exit_codes',[0]) else 'failed'),'mutation_occurred':False}

def git_diff_evidence(root:Path, authorized_paths:Sequence[str])->dict[str,Any]:
    def run(args): return subprocess.run(args,cwd=str(root),text=True,capture_output=True,timeout=10).stdout
    ns=run(['git','diff','--name-status']).splitlines()
    st=subprocess.run(['git','status','--short'],cwd=str(root),text=True,capture_output=True,timeout=10).stdout.splitlines()
    untracked=[]
    for l in st:
        if l.startswith('?? '):
            rel=' '.join(l.split()[1:])
            q=root/rel
            if rel.endswith('/') and q.is_dir():
                untracked += [x.relative_to(root).as_posix() for x in q.rglob('*') if x.is_file()]
            else:
                untracked.append(rel.rstrip('/'))
    stat=run(['git','diff','--stat']); excerpt=run(['git','diff','--',*authorized_paths])[:12000]
    changed=[line.split('\t')[-1] for line in ns if line.strip()] + untracked; auth=set(authorized_paths); unexpected=[p for p in changed if p not in auth]
    return {'changed_paths':changed,'added_paths':[l.split('\t')[-1] for l in ns if l.startswith('A')],'modified_paths':[l.split('\t')[-1] for l in ns if l.startswith('M')],'deleted_paths':[l.split('\t')[-1] for l in ns if l.startswith('D')],'renamed_paths':[l.split('\t')[-1] for l in ns if l.startswith('R')],'unexpected_paths':unexpected,'diff_stat':stat[:4000],'bounded_diff_excerpt':excerpt}

def verify_practical_repository_execution(pkg:Mapping[str,Any], evidence:Mapping[str,Any])->dict[str,Any]:
    tests=evidence.get('test_results',[]); test_failed=any(t.get('status')!='passed' for t in tests); unexpected=bool(evidence.get('unexpected_changes'))
    checks={'package_executed':evidence.get('execution_status')=='executed','authorization_consumed_once':evidence.get('authorization_consumption_count')==1,'mutations_succeeded':all(r.get('status') in {'succeeded','already_exists'} for r in evidence.get('operation_results',[])),'changed_paths_authorized':not unexpected,'tests_executed_when_required':not pkg.get('test_plan',{}).get('required') or bool(tests),'required_tests_passed':not test_failed}
    if unexpected: status='unexpected_change_detected'
    elif not all(v for k,v in checks.items() if k!='required_tests_passed'): status='verification_failed'
    elif test_failed: status='verified_with_test_failure'
    else: status='verified'
    return _canon({'schema':VERIFY_SCHEMA,'change_package_reference':_ref(pkg),'evidence_reference':_ref(evidence),'checks':checks,'verification_status':status,'completion_candidate':status=='verified','human_completion_accepted':False,'remaining_work':status!='verified'},'verification_fingerprint','verification_id','engineering-practical-verification-')

def practical_result(pkg=None,evidence=None,verification=None):
    return {'schema':'zero.engineering.practical_result.v1','mutation_executed':(evidence or {}).get('execution_status')=='executed','mutation_verified':(verification or {}).get('verification_status')=='verified','tests_required':(pkg or {}).get('test_plan',{}).get('required',False),'tests_passed':not any(t.get('status')!='passed' for t in (evidence or {}).get('test_results',[])),'unexpected_changes':(evidence or {}).get('unexpected_changes',[]),'acceptance_criteria_supported':(verification or {}).get('verification_status') in {'verified','verified_with_test_failure'},'remaining_work':(verification or {}).get('remaining_work',True),'completion_candidate':(verification or {}).get('completion_candidate',False),'human_completion_accepted':False,'session_completed':False,'next_iteration_candidate':(verification or {}).get('verification_status')=='verified_with_test_failure'}

def inspect_practical_state(bundle:Mapping[str,Any])->dict[str,Any]:
    pkg=bundle.get('work-entry/governed-change-package.json') or bundle.get('package')
    ev=bundle.get('execution/practical-execution-evidence.json') or bundle.get('evidence')
    ver=bundle.get('verification/practical-verification.json') or bundle.get('verification')
    if not pkg: return {'practical_task_runner_status':'not_initialized','next_governed_action':'requires_change_package'}
    ops=pkg.get('ordered_operations',[])
    return {'practical_task_runner_status':'initialized','change_package_status':pkg.get('package_status'),'operation_count':len(ops),'mutation_operation_count':sum(o.get('operation_type') in MUTATION_OPS for o in ops),'test_operation_count':sum(o.get('operation_type')=='run_bounded_test' for o in ops),'package_validation_status':'valid' if validate_governed_change_package(pkg)['valid'] else 'invalid','approval_binding_status':'attached' if pkg.get('approval_reference') else 'missing','authorization_binding_status':'attached' if pkg.get('authorization_scope_reference') else 'missing','workspace_drift_status':'not_detected','execution_status':(ev or {}).get('execution_status','not_started'),'evidence_status':(ev or {}).get('evidence_status','not_started'),'test_status':'failed' if any(t.get('status')!='passed' for t in (ev or {}).get('test_results',[])) else 'passed' if (ev or {}).get('test_results') else 'not_started','verification_status':(ver or {}).get('verification_status','not_started'),'unexpected_change_count':len((ev or {}).get('unexpected_changes',[])),'rollback_status':(ev or {}).get('rollback_status',{}).get('status','not_required'),'next_governed_action':resume_practical_state({'package':pkg,'evidence':ev,'verification':ver})['decision'],'timeline':['[Completed] Confirmed Specification','[Completed] Work Request','[Completed] Read-Only Analysis','[Completed] Change Package','[Pending]   Human Approval','[Pending]   Human Authorization','[Pending]   Adapter Admission','[Pending]   Explicit Execution','[Not Started] Verification','[Not Started] Completion Review']}

def resume_practical_state(bundle:Mapping[str,Any])->dict[str,Any]:
    decision='requires_change_package'
    if bundle.get('package'): decision='requires_approval'
    if bundle.get('approval'): decision='requires_authorization'
    if bundle.get('authorization'): decision='requires_execution_preparation'
    if bundle.get('admitted'): decision='requires_execution_confirmation'
    if bundle.get('evidence'): decision='requires_verification'
    if (bundle.get('verification') or {}).get('verification_status')=='verified': decision='already_verified'
    return {'schema':'zero.engineering.practical_resume.v1','decision':decision,'will_modify_repository':False,'will_execute_tests':False,'will_consume_authorization':False,'will_retry':False,'will_complete':False}
