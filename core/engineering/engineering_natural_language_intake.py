from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import canonical_json, fingerprint
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact, load_session_store
from core.engineering.engineering_work_entry import create_engineering_work_request, admit_engineering_work, create_work_coordination, persist_work_entry, WorkEntryError, _ref
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline

INTAKE_SCHEMA='zero.engineering.natural_language_intake.v1'; EVIDENCE_SCHEMA='zero.engineering.task_intake_repository_evidence.v1'; CANDIDATE_SCHEMA='zero.engineering.work_specification_candidate.v1'; CLARIFICATION_SCHEMA='zero.engineering.work_specification_clarification.v1'; RESPONSE_SCHEMA='zero.engineering.work_specification_clarification_response.v1'; CONFIRMATION_SCHEMA='zero.engineering.work_specification_confirmation.v1'
INTENTS={'bug_fix','feature_addition','behavior_change','refactor','test_addition','documentation_change','configuration_change','dependency_change','performance_improvement','security_hardening','repository_analysis','unknown','mixed'}
RISK_WORDS={'password':'credential_handling','密碼':'credential_handling','密码':'credential_handling','token':'credential_handling','secret':'credential_handling','migration':'data_migration','遷移':'data_migration','迁移':'data_migration','delete':'destructive_behavior','刪除':'destructive_behavior','删除':'destructive_behavior','deploy':'deployment','發布':'deployment','发布':'deployment','upgrade':'dependency_change','升級':'dependency_change','升级':'dependency_change','payment':'external_service_unclear','付款':'external_service_unclear','auth':'security_sensitive','登入':'security_sensitive','login':'security_sensitive'}
STATUS={'received','normalized','repository_evidence_required','repository_evidence_collected','specification_candidate_ready','clarification_required','awaiting_confirmation','confirmed','formalized','blocked','failed','invalid','closed'}
STORE_FILES={'intake':'work-entry/natural-language-intake.json','evidence':'work-entry/intake-repository-evidence.json','candidate':'work-entry/specification-candidate.json','clarification':'work-entry/specification-clarification.json','response':'work-entry/specification-clarification-response.json','confirmation':'work-entry/specification-confirmation.json'}
SAFE_RE=re.compile(r'^[A-Za-z0-9._/\\:-]+$')

class NaturalLanguageIntakeError(ValueError):
    def __init__(self, code:str): super().__init__(code); self.code=code

def _stable(body:Mapping[str,Any], fp_key:str, id_key:str, prefix:str)->dict[str,Any]:
    base={k:v for k,v in dict(body).items() if k not in {fp_key,id_key}}
    fp=fingerprint(base); return {**base,fp_key:fp,id_key:prefix+fp[:32]}

def _ensure_safe_rel(p:str)->str:
    s=str(p).replace('\\','/').strip()
    if not s or s.startswith('/') or '..' in s.split('/') or not SAFE_RE.match(s): raise NaturalLanguageIntakeError('unsafe_path_rejected')
    return s

def normalize_engineering_task_statement(statement:str)->dict[str,str]:
    original=str(statement)
    nfkc=unicodedata.normalize('NFKC', original)
    protected=[]
    def keep(m): protected.append(m.group(0)); return f'@@Q{len(protected)-1}@@'
    work=re.sub(r'(["“”\'「『`])([^"“”\'」』`]*)(["“”\'」』`])', keep, nfkc)
    work=re.sub(r'[，、﹐]', ',', work); work=re.sub(r'[。｡]', '.', work); work=re.sub(r'[：﹕]', ':', work); work=re.sub(r'[；﹔]', ';', work)
    work=re.sub(r'\s+', ' ', work).strip()
    for i,v in enumerate(protected): work=work.replace(f'@@Q{i}@@', v)
    return {'original_statement':original,'normalized_statement':work}

def detect_language(s:str)->str:
    has_cjk=bool(re.search(r'[\u4e00-\u9fff]',s)); has_en=bool(re.search(r'[A-Za-z]',s))
    return 'mixed' if has_cjk and has_en else 'zh' if has_cjk else 'en' if has_en else 'unknown'

MATCH_KINDS={'short_ascii_alias','full_ascii_word','multiword_phrase','identifier_token','non_ascii_phrase'}
INTENT_TERMS={
    'test_addition':[('test','short_ascii_alias'),('tests/','identifier_token'),('測試','non_ascii_phrase'),('测试','non_ascii_phrase')],
    'bug_fix':[('fix','short_ascii_alias'),('bug','short_ascii_alias'),('error','full_ascii_word'),('broken','full_ascii_word'),('修正','non_ascii_phrase'),('錯誤','non_ascii_phrase'),('错误','non_ascii_phrase'),('沒反應','non_ascii_phrase'),('没反应','non_ascii_phrase'),('失敗','non_ascii_phrase'),('失败','non_ascii_phrase')],
    'feature_addition':[('add','short_ascii_alias'),('新增','non_ascii_phrase'),('增加','non_ascii_phrase'),('feature','full_ascii_word'),('支援','non_ascii_phrase'),('支持','non_ascii_phrase')],
    'documentation_change':[('docs/','identifier_token'),('document','full_ascii_word'),('documentation','full_ascii_word'),('readme','full_ascii_word'),('文件','non_ascii_phrase'),('說明','non_ascii_phrase'),('说明','non_ascii_phrase')],
    'security_hardening':[('security','full_ascii_word'),('secure','full_ascii_word'),('password','full_ascii_word'),('secret','full_ascii_word'),('token','full_ascii_word'),('密碼','non_ascii_phrase'),('密码','non_ascii_phrase'),('認證','non_ascii_phrase'),('认证','non_ascii_phrase'),('授權','non_ascii_phrase'),('授权','non_ascii_phrase')],
    'dependency_change':[('dependency','full_ascii_word'),('dependencies','full_ascii_word'),('upgrade','full_ascii_word'),('package','full_ascii_word'),('依賴','non_ascii_phrase'),('依赖','non_ascii_phrase'),('升級','non_ascii_phrase'),('升级','non_ascii_phrase')],
    'refactor':[('refactor','full_ascii_word'),('重構','non_ascii_phrase'),('重构','non_ascii_phrase')],
    'performance_improvement':[('performance improvement','multiword_phrase'),('improve performance','multiword_phrase'),('optimize performance','multiword_phrase'),('performance_improvement','identifier_token'),('performance','full_ascii_word'),('perf','short_ascii_alias'),('效能改善','non_ascii_phrase'),('性能優化','non_ascii_phrase'),('改善效能','non_ascii_phrase'),('速度','non_ascii_phrase'),('效能','non_ascii_phrase'),('性能','non_ascii_phrase')],
    'configuration_change':[('config','full_ascii_word'),('configuration','full_ascii_word'),('設定','non_ascii_phrase'),('配置','non_ascii_phrase')],
    'repository_analysis':[('analyze repository','multiword_phrase'),('repository analysis','multiword_phrase'),('分析程式庫','non_ascii_phrase'),('分析仓库','non_ascii_phrase')],
}

def _intent_term_matches(statement:str, term:str, kind:str)->list[dict[str,Any]]:
    if kind not in MATCH_KINDS: return []
    normalized=statement.lower(); needle=term.lower()
    matches=[]
    for found in re.finditer(re.escape(needle),normalized):
        start,end=found.span(); left=normalized[start-1] if start else ''; right=normalized[end] if end<len(normalized) else ''
        left_ok=not left.isalnum(); right_ok=needle.endswith(('/','_','-')) or not right.isalnum()
        if kind=='non_ascii_phrase' or (left_ok and right_ok): matches.append({'matched_term':term,'match_kind':kind,'matched_span':[start,end],'normalization_basis':'NFKC_then_lowercase'})
    return matches

def classify_engineering_intent(statement:str)->dict[str,Any]:
    s=unicodedata.normalize('NFKC',statement).lower(); hits=[]
    for intent, terms in INTENT_TERMS.items():
        matches=[match for term,kind in terms for match in _intent_term_matches(s,term,kind)]
        if matches: hits.append((intent,matches))
    if len({h[0] for h in hits})>1 and any(marker in s for marker in (',',';','、',' and ','以及',' with explicit ')): primary='mixed'
    elif any(intent=='performance_improvement' and any(match['matched_term']=='perf' for match in matches) for intent,matches in hits): primary='performance_improvement'
    elif hits: primary=hits[0][0]
    else: primary='unknown'
    secondary=sorted({h[0] for h in hits if h[0]!=primary})
    conf='high' if primary!='unknown' and len(hits)==1 else 'medium' if primary!='unknown' else 'unknown'
    return {'primary_intent':primary,'secondary_intents':secondary,'confidence_band':conf,'classification_evidence':[{'intent':intent,'matched_terms':[match['matched_term'] for match in matches],'matches':matches} for intent,matches in hits],'unsupported_elements':[] if primary!='unknown' else ['unsupported_intent']}

def _extract_refs(statement:str)->dict[str,list[str]]:
    paths=sorted(set(m.group(0).strip('.,;:，。；') for m in re.finditer(r'(?:(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+)', statement)))
    files=sorted(set(m.group(0) for m in re.finditer(r'\b[A-Za-z0-9_.-]+\.(?:py|js|ts|tsx|jsx|md|json|yaml|yml|html|css|toml)\b', statement)))
    symbols=sorted(set(m.group(1) for m in re.finditer(r'`([A-Za-z_][A-Za-z0-9_]*)`', statement)))
    return {'paths':paths,'filenames':files,'symbols':symbols}

def build_bounded_repository_evidence(statement:str, repository:str|Path='.') -> dict[str,Any]:
    root=Path(repository).resolve(); refs=_extract_refs(statement); observed=[]; unresolved=[]; tests=[]; configs=[]; symbols=[]; excluded=['.git','node_modules','.venv','__pycache__']
    for p in refs['paths']:
        rel=_ensure_safe_rel(p); target=root/rel
        (observed if target.exists() else unresolved).append(rel)
    for name in refs['filenames']:
        matches=[]
        for m in root.rglob(name):
            if any(part in excluded for part in m.relative_to(root).parts): continue
            matches.append(m.relative_to(root).as_posix())
            if len(matches)>=20: break
        observed.extend(matches); unresolved.extend([] if matches else [name])
    likely=[]
    lower=statement.lower()
    for term in ['login','auth','登入','docs','test','payment','password']:
        if term in lower:
            key={'登入':'login','密碼':'password'}.get(term,term)
            for m in root.rglob(f'*{key}*'):
                if any(part in excluded for part in m.relative_to(root).parts): continue
                likely.append(m.relative_to(root).as_posix())
                if len(likely)>=25: break
    for pat in ['pyproject.toml','package.json','pytest.ini','README.md']:
        if (root/pat).exists(): configs.append(pat)
    for m in root.rglob('test*'):
        if len(tests)>=20: break
        if any(part in excluded for part in m.relative_to(root).parts): continue
        tests.append(m.relative_to(root).as_posix())
    body={'schema':EVIDENCE_SCHEMA,'repository_identity':{'repository_root_fingerprint':fingerprint(str(root))},'admitted_root':str(root),'requested_evidence_scope':{'explicit_paths':refs['paths'],'exact_filenames':refs['filenames'],'exact_symbols':refs['symbols'],'bounded':True,'max_matches_per_kind':25},'observed_matching_paths':sorted(set(observed+likely))[:50],'observed_symbols':symbols,'observed_tests':sorted(set(tests)),'observed_configuration':sorted(set(configs)),'unresolved_references':sorted(set(unresolved)),'excluded_paths':excluded,'evidence_limitations':['read_only_bounded_scan','no_project_tests_executed','no_arbitrary_commands_executed']}
    return _stable(body,'evidence_fingerprint','evidence_id','engineering-intake-evidence-')

def _risk(statement:str, intent:Mapping[str,Any])->dict[str,Any]:
    reasons=sorted({v for k,v in RISK_WORDS.items() if k in statement.lower()})
    if intent.get('primary_intent')=='unknown': reasons.append('unknown_intent')
    level='critical' if 'data_migration' in reasons and 'credential_handling' in reasons else 'high' if any(r in reasons for r in ['credential_handling','data_migration','destructive_behavior','deployment']) else 'moderate' if reasons else 'low'
    return {'risk_level':level,'reasons':sorted(set(reasons)),'risk_acknowledgement_required':level in {'high','critical'} or 'unknown_intent' in reasons}

def build_specification_candidate(intake:Mapping[str,Any], evidence:Mapping[str,Any], *, previous_candidate:Mapping[str,Any]|None=None, response:Mapping[str,Any]|None=None)->dict[str,Any]:
    stmt=intake['normalized_statement']; intent=intake['intent_classification']; risk=_risk(stmt,intent); observed={'reported_problem':stmt,'repository_evidence':evidence.get('observed_matching_paths',[])}
    included=[p for p in evidence.get('observed_matching_paths',[]) if p in evidence.get('requested_evidence_scope',{}).get('explicit_paths',[]) or '/' in p][:20]
    assumptions=['repository matches bounded evidence only']
    unresolved=[]
    if evidence.get('unresolved_references'): unresolved.append('repository reference not found: '+', '.join(evidence['unresolved_references']))
    if intent.get('primary_intent') in {'unknown','mixed'} or intent.get('confidence_band') in {'low','unknown'}: unresolved.append('task intent requires human clarification')
    if (not included and intent.get('primary_intent') not in {'documentation_change','test_addition'}) or (intent.get('primary_intent')=='bug_fix' and 'login' in stmt.lower() and len(evidence.get('observed_matching_paths',[]))>1): unresolved.append('repository target ambiguous')
    if risk['risk_acknowledgement_required']: unresolved.append('risk acknowledgement required')
    if response:
        included=sorted(set(included+[_ensure_safe_rel(x) for x in response.get('scope_corrections',{}).get('included_paths',[])]))
        assumptions+=list(response.get('confirmed_assumptions',[]))
        unresolved=[q for q in unresolved if 'repository target ambiguous' not in q] if included else unresolved
    ac=[{'criterion_id':'behavior','description':'Implement the confirmed user-visible behavior without expanding scope.','verification_method':'human_review_or_targeted_test','evidence_required':['confirmed_specification'],'status':'proposed'},{'criterion_id':'test','description':'Add or update relevant tests when scope allows.','verification_method':'targeted_test','evidence_required':['test_output_after_execution'],'status':'proposed'},{'criterion_id':'scope','description':'Changes remain within confirmed included paths and constraints.','verification_method':'diff_review','evidence_required':['confirmed_scope'],'status':'proposed'},{'criterion_id':'regression','description':'Existing related behavior is not regressed.','verification_method':'targeted_regression','evidence_required':['regression_evidence'],'status':'proposed'},{'criterion_id':'safety','description':'No approval, authorization, execution, or repository mutation is implied by this candidate.','verification_method':'artifact_review','evidence_required':['governance_artifacts'],'status':'proposed'}]
    status='clarification_required' if unresolved else 'ready_for_confirmation'
    body={'schema':CANDIDATE_SCHEMA,'version':1 if not previous_candidate else int(previous_candidate.get('version',1))+1,'previous_candidate_reference':_ref(previous_candidate,'specification_candidate_fingerprint') if previous_candidate else None,'intake_reference':_ref(intake,'intake_fingerprint'),'task_title':stmt[:80],'problem_statement':{'observed':observed,'desired':'Human-confirmed desired behavior is required before work request formalization.','unknown_root_cause':True},'desired_outcome':'Await human confirmation of desired outcome and acceptance criteria.','primary_intent':intent.get('primary_intent'),'repository_scope':{'included_paths':[{'path':p,'status':'candidate_not_confirmed'} for p in included],'excluded_paths':evidence.get('excluded_paths',[]),'scope_confirmed':False},'included_paths':included,'excluded_paths':evidence.get('excluded_paths',[]),'target_components':[{'path':p,'basis':'repository_evidence','confirmed':False} for p in included],'acceptance_criteria':ac,'validation_expectations':['proposed_targeted_validation_only'],'risk_hints':[risk],'assumptions':assumptions,'unresolved_questions':unresolved,'repository_evidence_references':[_ref(evidence,'evidence_fingerprint')],'requested_mode':intake.get('requested_mode','governed_delivery'),'execution_policy_hint':{'candidate_has_authority':False,'approval_granted':False,'authorization_granted':False,'execution_allowed':False},'candidate_status':status,'is_formal_work_request':False}
    return _stable(body,'specification_candidate_fingerprint','specification_candidate_id','engineering-spec-candidate-')

def assess_specification_clarification(candidate:Mapping[str,Any])->dict[str,Any]:
    blocks=list(candidate.get('unresolved_questions',[])); questions=[]
    if any('target ambiguous' in b for b in blocks): questions.append('Which repository paths or components are in scope, and which are explicitly out of scope?')
    if any('intent' in b for b in blocks): questions.append('What is the single primary engineering goal for this task?')
    if any('risk acknowledgement' in b for b in blocks): questions.append('Please acknowledge the high or unknown risk and provide constraints for credentials, data migration, or destructive behavior.')
    if not questions and candidate.get('candidate_status')=='ready_for_confirmation': status='not_required'
    else:
        status='required'; questions=questions or ['What observable behavior and verification evidence should define completion?']
    body={'schema':CLARIFICATION_SCHEMA,'specification_candidate_reference':_ref(candidate,'specification_candidate_fingerprint'),'clarification_status':status,'required_questions':questions,'optional_questions':['Are there related tests that should be included in validation?'],'blocking_ambiguities':blocks,'safe_defaults':['Do not expand scope without explicit human correction.'],'prohibited_assumptions':['Do not assume root cause.','Do not treat candidate as approval.','Do not execute before authorization.'],'human_response_reference':None}
    return _stable(body,'clarification_fingerprint','clarification_id','engineering-spec-clarification-')

def apply_human_clarification_response(candidate:Mapping[str,Any], clarification:Mapping[str,Any], response:Mapping[str,Any])->tuple[dict[str,Any],dict[str,Any]]:
    if not response.get('human_actor'): raise NaturalLanguageIntakeError('missing_human_actor')
    if response.get('clarification_reference',{}).get('artifact_identity')!=clarification.get('clarification_id'): raise NaturalLanguageIntakeError('wrong_clarification_reference')
    allowed={'clarification_reference','human_actor','answers','confirmed_assumptions','rejected_assumptions','additional_constraints','scope_corrections','acceptance_corrections'}
    if set(response)-allowed: raise NaturalLanguageIntakeError('unrelated_field_change_rejected')
    resp=_stable({'schema':RESPONSE_SCHEMA,**response},'clarification_response_fingerprint','clarification_response_id','engineering-spec-clarification-response-')
    intake={'schema':INTAKE_SCHEMA,'intake_id':candidate['intake_reference']['artifact_identity'],'intake_fingerprint':candidate['intake_reference']['artifact_fingerprint'],'normalized_statement':candidate['task_title'],'intent_classification':{'primary_intent':candidate['primary_intent']},'requested_mode':candidate.get('requested_mode')}
    ev={'schema':EVIDENCE_SCHEMA,'evidence_id':candidate['repository_evidence_references'][0]['artifact_identity'],'evidence_fingerprint':candidate['repository_evidence_references'][0]['artifact_fingerprint'],'observed_matching_paths':candidate.get('included_paths',[]),'excluded_paths':candidate.get('excluded_paths',[]),'unresolved_references':[],'requested_evidence_scope':{}}
    new=build_specification_candidate(intake,ev,previous_candidate=candidate,response=resp)
    return resp,new

def confirm_specification(candidate:Mapping[str,Any], confirmation:Mapping[str,Any])->dict[str,Any]:
    if not confirmation.get('human_actor') or str(confirmation.get('human_actor')).startswith('zero.test.'): raise NaturalLanguageIntakeError('missing_human_actor')
    if confirmation.get('specification_candidate_reference',{}).get('artifact_identity')!=candidate.get('specification_candidate_id'): raise NaturalLanguageIntakeError('wrong_candidate_reference')
    if candidate.get('candidate_status')!='ready_for_confirmation': raise NaturalLanguageIntakeError('candidate_not_ready_rejected')
    if candidate.get('unresolved_questions'): raise NaturalLanguageIntakeError('unresolved_blocker_rejected')
    if any(r.get('risk_acknowledgement_required') for r in candidate.get('risk_hints',[])) and not confirmation.get('risk_acknowledgement'): raise NaturalLanguageIntakeError('high_risk_without_acknowledgement_rejected')
    cs=sorted(confirmation.get('confirmed_scope',[])); inc=sorted(candidate.get('included_paths',[]))
    if cs!=inc: raise NaturalLanguageIntakeError('scope_mismatch_rejected')
    status={'confirm':'confirmed','reject':'rejected','return_for_clarification':'clarification_required'}.get(confirmation.get('decision'),'invalid')
    body={'schema':CONFIRMATION_SCHEMA,**confirmation,'confirmation_status':status,'approval_granted':False,'authorization_granted':False,'execution_permission':False,'next_governed_action':'create_formal_work_request' if status=='confirmed' else 'clarification'}
    return _stable(body,'confirmation_fingerprint','confirmation_id','engineering-spec-confirmation-')

def create_formal_work_request_from_confirmed_specification(candidate:Mapping[str,Any], confirmation:Mapping[str,Any], *, repository_root_reference='.', repository_identity:Mapping[str,Any]|None=None)->dict[str,Any]:
    if confirmation.get('confirmation_status')!='confirmed': raise NaturalLanguageIntakeError('no_confirmation_no_formalization')
    if not confirmation.get('human_actor'): raise NaturalLanguageIntakeError('missing_human_actor')
    ref=confirmation.get('specification_candidate_reference',{})
    if ref.get('artifact_identity')!=candidate.get('specification_candidate_id') or ref.get('artifact_fingerprint')!=candidate.get('specification_candidate_fingerprint'): raise NaturalLanguageIntakeError('wrong_candidate_reference')
    if candidate.get('candidate_status')!='ready_for_confirmation' or candidate.get('unresolved_questions'): raise NaturalLanguageIntakeError('unconfirmed_specification')
    scope=list(confirmation.get('confirmed_scope',[]))
    if not scope or sorted(scope)!=sorted(candidate.get('included_paths',[])): raise NaturalLanguageIntakeError('scope_mismatch_rejected')
    criteria=list(confirmation.get('confirmed_acceptance_criteria') or [])
    if not criteria or not str(candidate.get('desired_outcome','')).strip(): raise NaturalLanguageIntakeError('incomplete_confirmed_specification')
    acc='confirmed acceptance criteria count: '+str(len(criteria))
    req=create_engineering_work_request(request_statement=candidate['task_title'],repository_identity=repository_identity or {'repository_id':'default'},repository_root_reference=repository_root_reference,requested_scope=scope or ['docs/status.txt'],constraints=list(confirmation.get('confirmed_constraints',[]))+['lineage:'+confirmation['confirmation_id']],acceptance_intent=acc,risk_classification=candidate.get('risk_hints',[{}])[0].get('risk_level','unknown'),requested_mode=candidate.get('requested_mode','governed_delivery'),source_actor_reference={'specification_decision_reference':_ref(confirmation,'confirmation_fingerprint'),'natural_language_lineage':candidate.get('intake_reference')})
    intake=admit_engineering_work(req); coord=create_work_coordination(req,intake); pipe=create_read_only_pipeline(req,intake,coord)
    return {'work_request':req,'work_intake':intake,'coordination':coord,'read_only_pipeline':pipe,'prepared':False,'approved':False,'authorized':False,'executed':False,'lineage':{'specification_candidate_reference':_ref(candidate,'specification_candidate_fingerprint'),'confirmation_reference':_ref(confirmation,'confirmation_fingerprint')}}

def start_natural_language_intake(statement:str, *, store_root:str|Path='.zero-engineering-sessions', repository:str|Path='.', repo_id='default', requested_mode='governed_delivery')->dict[str,Any]:
    norm=normalize_engineering_task_statement(statement); intent=classify_engineering_intent(norm['normalized_statement']); evidence=build_bounded_repository_evidence(norm['normalized_statement'],repository); risk=_risk(norm['normalized_statement'],intent)
    body={'schema':INTAKE_SCHEMA,'original_statement':norm['original_statement'],'normalized_statement':norm['normalized_statement'],'input_language':detect_language(norm['normalized_statement']),'intent_classification':intent,'repository_reference':{'repository_id':repo_id,'repository_root':str(Path(repository).resolve())},'requested_mode':requested_mode,'risk_hint':risk,'intake_status':'repository_evidence_collected','specification_candidate_reference':None,'clarification_reference':None,'confirmation_reference':None,'formal_work_request_reference':None,'blocked_reasons':[],'next_governed_action':'build_specification_candidate'}
    intake=_stable(body,'intake_fingerprint','intake_id','engineering-nl-intake-')
    candidate=build_specification_candidate(intake,evidence); clar=assess_specification_clarification(candidate)
    final_status='clarification_required' if clar['clarification_status']=='required' else 'awaiting_confirmation'
    intake=_stable({**{k:v for k,v in intake.items() if k not in {'intake_fingerprint','intake_id'}},'intake_status':final_status,'specification_candidate_reference':_ref(candidate,'specification_candidate_fingerprint'),'clarification_reference':_ref(clar,'clarification_fingerprint'),'next_governed_action':'clarification' if final_status=='clarification_required' else 'confirm_specification'},'intake_fingerprint','intake_id','engineering-nl-intake-')
    sid=intake['intake_id'];
    for key,val in [('intake',intake),('evidence',evidence),('candidate',candidate),('clarification',clar)]: write_session_artifact(store_root,sid,STORE_FILES[key],val); assert read_session_artifact(store_root,sid,STORE_FILES[key])==val
    return {'natural_language_intake':intake,'repository_evidence':evidence,'specification_candidate':candidate,'clarification':clar,'formal_work_request_created':False}

def _latest_intake_dir(store_root:Path, session_id:str|None=None):
    if session_id: return session_id
    if not store_root.exists(): raise NaturalLanguageIntakeError('missing_artifact')
    dirs=[p.name for p in sorted(store_root.iterdir()) if p.is_dir() and p.name.startswith('engineering-nl-intake-')]
    if not dirs: raise NaturalLanguageIntakeError('missing_artifact')
    return dirs[-1]

def load_intake_bundle(store_root:str|Path='.zero-engineering-sessions', session_id:str|None=None)->dict[str,Any]:
    sid=_latest_intake_dir(Path(store_root),session_id); return load_session_store(store_root,sid)

def inspect_natural_language_intake(store_root:str|Path='.zero-engineering-sessions', session_id:str|None=None)->dict[str,Any]:
    try: b=load_intake_bundle(store_root,session_id)
    except NaturalLanguageIntakeError: return {'natural_language_intake_status':'not_initialized','next_governed_action':'intake'}
    i=b.get(STORE_FILES['intake'],{}); c=b.get(STORE_FILES['candidate'],{}); cl=b.get(STORE_FILES['clarification'],{}); cf=b.get(STORE_FILES['confirmation'],{}); f=b.get('work-entry/request.json')
    tl=['Natural-Language Intake','Repository Evidence','Specification Candidate','Human Clarification','Specification Confirmation','Formal Work Request','Work Coordination']
    return {'natural_language_intake_status':i.get('intake_status','not_initialized'),'original_statement':i.get('original_statement'),'normalized_statement':i.get('normalized_statement'),'intent_classification':i.get('intent_classification'),'repository_evidence_status':'collected' if b.get(STORE_FILES['evidence']) else 'not_started','specification_candidate_status':c.get('candidate_status','not_started'),'specification_confirmation_status':cf.get('confirmation_status','not_started'),'clarification_status':cl.get('clarification_status','not_started'),'blocking_question_count':len(cl.get('required_questions',[])),'confirmation_status':cf.get('confirmation_status','not_started'),'formal_work_request_status':'created' if f else 'not_started','work_request_id':(f or {}).get('work_request_id'),'work_request_fingerprint':(f or {}).get('work_request_fingerprint'),'repository_analysis_reference_status':'available' if b.get(STORE_FILES['evidence']) else 'missing','missing_linkage_reason':None if f else ('requires_specification_confirmation' if cf.get('confirmation_status')!='confirmed' else 'missing_work_request'),'next_governed_action':i.get('next_governed_action'),'timeline':[{'stage':x,'status':'Completed' if x in tl[:3] else 'Pending' if x=='Human Clarification' and cl.get('clarification_status')=='required' else 'Not Started'} for x in tl]}

def resume_natural_language_intake(store_root:str|Path='.zero-engineering-sessions', session_id:str|None=None)->dict[str,Any]:
    ins=inspect_natural_language_intake(store_root,session_id); st=ins.get('natural_language_intake_status')
    decision={'not_initialized':'requires_repository_evidence','clarification_required':'requires_human_clarification','awaiting_confirmation':'requires_specification_confirmation','confirmed':'requires_formalization','formalized':'already_formalized'}.get(st,'blocked' if st=='blocked' else 'invalid')
    return {'resume_decision':decision,'recommended_command':{'requires_human_clarification':'clarification','requires_specification_confirmation':'specification','requires_formalization':'formalize'}.get(decision,'intake-status'),'will_assume_requirements':False,'will_confirm_specification':False,'will_create_approval':False,'will_authorize':False,'will_execute':False,'will_complete':False,'inspection':ins}

def persist_formalized(store_root:str|Path, intake_session_id:str, formalized:Mapping[str,Any])->dict[str,Any]:
    sid=formalized['coordination']['runtime_session_reference']['artifact_identity']; persist_work_entry(store_root,sid,request=formalized['work_request'],intake=formalized['work_intake'],coordination=formalized['coordination']); write_session_artifact(store_root,sid,'work-entry/pipeline.json',formalized['read_only_pipeline'])
    b=load_intake_bundle(store_root,intake_session_id); i=b[STORE_FILES['intake']]; conf=b.get(STORE_FILES['confirmation'])
    ni=_stable({**{k:v for k,v in i.items() if k not in {'intake_fingerprint','intake_id'}},'intake_status':'formalized','confirmation_reference':_ref(conf,'confirmation_fingerprint') if conf else None,'formal_work_request_reference':_ref(formalized['work_request'],'work_request_fingerprint'),'next_governed_action':'requires_repository_admission'},'intake_fingerprint','intake_id','engineering-nl-intake-')
    write_session_artifact(store_root,intake_session_id,STORE_FILES['intake'],ni)
    persist_work_entry(store_root,intake_session_id,request=formalized['work_request'],intake=formalized['work_intake'],coordination=formalized['coordination'])
    write_session_artifact(store_root,intake_session_id,'work-entry/pipeline.json',formalized['read_only_pipeline'])
    return {'intake_session_id':intake_session_id,'work_session_id':sid,'formalization_status':'formalized',**formalized}
