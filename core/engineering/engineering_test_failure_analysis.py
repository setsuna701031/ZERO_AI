from __future__ import annotations
import re
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import fingerprint
from core.engineering.engineering_practical_task_runner import _ref
FAILURE_SCHEMA='zero.engineering.test_failure_evidence.v1'
MAX_FRAMES=8; MAX_TEXT=300
KINDS={'assertion_failure','exception','collection_error','import_error','timeout','setup_failure','teardown_failure','unknown'}

def canon(body, fp_key, id_key, prefix):
    b=dict(body); fp=fingerprint(b); b[fp_key]=fp; b[id_key]=prefix+fp[:24]; return b

def _clip(s): return (s or '').replace('\x00','')[:MAX_TEXT]
def parse_pytest_output(output:str, *, repository_root:str='.'):
    try:
        out=str(output or '')
        if 'timed out' in out.lower(): kind='timeout'
        elif 'ImportError' in out or 'ModuleNotFoundError' in out: kind='import_error'
        elif 'ERROR collecting' in out or 'collected 0 items / 1 error' in out: kind='collection_error'
        elif 'AssertionError' in out or re.search(r'^E\s+assert ', out, re.M): kind='assertion_failure'
        elif 'Exception' in out or re.search(r'^E\s+\w+Error', out, re.M): kind='exception'
        else: kind='unknown'
        nodes=re.findall(r'((?:tests|test)/[^\s:]+\.py::[A-Za-z0-9_\[\]-]+)', out) or re.findall(r'FAILED\s+([^\s]+::[^\s]+)', out)
        if not nodes:
            m=re.search(r'((?:tests|test)/[^\s]+\.py)', out); nodes=[m.group(1)+'::unknown'] if m else ['unknown::unknown']
        frames=[]; paths=[]
        for m in re.finditer(r'File "([^"]+)", line (\d+), in ([^\n]+)', out):
            p=m.group(1).replace('\\','/')
            if '/site-packages/' in p or p.startswith('/usr/'): continue
            idx=p.find('tests/'); idx2=p.find('core/') if idx<0 else idx
            idx3=p.find('app/') if idx2<0 else idx2
            rel=p[idx3:] if idx3>=0 else p.lstrip('./')
            if rel.startswith('../') or rel.startswith('/'): continue
            frames.append({'path':rel,'line':int(m.group(2)),'function':_clip(m.group(3))}); paths.append(rel)
            if len(frames)>=MAX_FRAMES: break
        em=re.search(r'^E\s+([A-Za-z_][\w.]*Error|Exception|ImportError|ModuleNotFoundError|AssertionError)', out, re.M)
        assertion='\n'.join([_clip(x[2:].strip()) for x in out.splitlines() if x.startswith('E ')][:4])
        failures=[]
        for n in sorted(set(nodes)):
            tf=n.split('::')[0]; tn=n.split('::')[-1]
            failures.append({'test_node':n,'test_file':tf,'test_name':tn,'failure_kind':kind,'exception_type':em.group(1) if em else ('AssertionError' if kind=='assertion_failure' else None),'assertion_summary':assertion,'expected_summary':_clip((re.search(r'[-] (.+)', assertion or '') or [None,''])[1]),'actual_summary':_clip((re.search(r'[+] (.+)', assertion or '') or [None,''])[1]),'relevant_traceback_frames':frames,'referenced_source_paths':sorted(set(paths)),'output_truncated':len(out)>12000})
        return failures
    except Exception:
        return [{'test_node':'unknown::unknown','test_file':'unknown','test_name':'unknown','failure_kind':'unknown','exception_type':None,'assertion_summary':'','expected_summary':'','actual_summary':'','relevant_traceback_frames':[],'referenced_source_paths':[],'output_truncated':False}]

def correlate_suspected_paths(failed_tests, changed_paths, confirmed_scope=()):
    allowed=set(confirmed_scope or changed_paths or []) ; rows=[]
    candidates=[]
    for f in failed_tests:
        candidates += f.get('referenced_source_paths',[])+[f.get('test_file')]
    candidates += list(changed_paths or [])
    for p in sorted(set(x for x in candidates if x)):
        if allowed and not any(p==s or p.startswith(str(s).rstrip('/')+'/') for s in allowed): continue
        tb=any(p in f.get('referenced_source_paths',[]) for f in failed_tests); ch=p in (changed_paths or [])
        reasons=[]
        if tb: reasons.append('traceback_repository_path')
        if ch: reasons.append('changed_in_current_execution')
        if p.endswith('.py') and not p.startswith('tests/'): reasons.append('production_source_candidate')
        band='high' if tb and ch else 'medium' if tb or ch else 'low'
        rows.append({'path':p,'evidence_reasons':reasons,'confidence_band':band,'changed_in_current_execution':ch,'traceback_referenced':tb,'dependency_related':False})
    return rows

def build_test_failure_evidence(*, execution:Mapping[str,Any], verification:Mapping[str,Any], test_set:Mapping[str,Any], repository_evidence:Sequence[Mapping[str,Any]]|None=None, changed_paths:Sequence[str]=(), confirmed_scope:Sequence[str]=()):
    failed=[]
    for r in test_set.get('ordered_results',[]):
        if r.get('status') not in {'passed','not_executed'}:
            failed += parse_pytest_output((r.get('stdout') or r.get('stdout_summary') or '')+'\n'+(r.get('stderr') or r.get('stderr_summary') or ''), repository_root='.')
    suspected=correlate_suspected_paths(failed, changed_paths, confirmed_scope)
    return canon({'schema':FAILURE_SCHEMA,'execution_reference':_ref(execution),'verification_reference':_ref(verification),'test_set_reference':_ref(test_set),'failed_tests':failed,'repository_evidence':list(repository_evidence or []),'changed_paths':list(changed_paths),'suspected_related_paths':suspected,'confirmed_root_cause':None,'root_cause_status':'suspected' if suspected else 'unknown','limitations':['bounded pytest output only','root cause is not confirmed','no repair authorization is granted'],'evidence_status':'collected'},'evidence_fingerprint','evidence_id','engineering-test-failure-evidence-')
