from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_multifile_coding_workflow import canon, classify_role
from core.engineering.engineering_practical_task_runner import _ref, safe_path

INTAKE_SCHEMA='zero.engineering.patch_authoring_intake.v1'
SNAPSHOT_SCHEMA='zero.engineering.patch_authoring_source_snapshot.v1'
EDIT_SCHEMA='zero.engineering.file_edit_candidate.v1'
DIFF_SCHEMA='zero.engineering.candidate_diff_artifact.v1'
VALIDATION_SCHEMA='zero.engineering.patch_authoring_validation.v1'
REVIEW_SCHEMA='zero.engineering.authored_patch_review.v1'
AUTHORITY={'may_modify_repository':False,'may_execute':False,'may_apply_patch':False,'may_create_change_package':False,'may_approve':False,'may_authorize':False,'may_retry':False,'may_complete':False}
STORE_FILES={'intake':'patch-authoring/intake.json','snapshots':'patch-authoring/source-snapshots.json','file_edits':'patch-authoring/file-edits.json','test_edits':'patch-authoring/test-edits.json','diff':'patch-authoring/candidate-diff.json','validation':'patch-authoring/validation.json','review':'patch-authoring/review.json'}
EDIT_KINDS={'replace_exact_text','replace_file_content','append_text','remove_exact_text','create_text_file'}
MAX_FILES=8; MAX_FILE_BYTES=131072; MAX_TOTAL_BYTES=524288
PROHIBITED_CONTENT=('ev'+'al(','ex'+'ec(','os.'+'system','shell'+'=true','subprocess.'+'run(','subprocess.'+'popen(')
PROHIBITED_KEYS={'command','argv','shell','authorization','change_package','operations','ordered_operations','apply','execute'}

class PatchAuthoringError(ValueError):
    def __init__(self,code): super().__init__(code); self.code=code

def build_patch_authoring_intake(*,patch_candidate:Mapping[str,Any],patch_validation:Mapping[str,Any],human_patch_review:Mapping[str,Any],repair_strategy:Mapping[str,Any],impact_analysis:Mapping[str,Any],repository_identity:Mapping[str,Any],confirmed_scope:Sequence[str],iteration_reference:Mapping[str,Any],session_id:str)->dict[str,Any]:
    if patch_validation.get('validation_status')!='valid': raise PatchAuthoringError('patch_validation_required')
    if human_patch_review.get('decision')!='confirmed': raise PatchAuthoringError('patch_review_not_confirmed')
    if not human_patch_review.get('human_actor'): raise PatchAuthoringError('human_actor_required')
    if human_patch_review.get('patch_candidate_reference')!=_ref(patch_candidate): raise PatchAuthoringError('stale_patch_candidate')
    patch_ids={x.get('patch_item_id') for x in patch_candidate.get('ordered_patch_items',[])}
    confirmed_ids=set(human_patch_review.get('confirmed_patch_item_ids') or [])
    confirmed_paths=set(human_patch_review.get('confirmed_paths') or [])
    if confirmed_ids!=patch_ids or confirmed_paths!={x.get('path') for x in patch_candidate.get('ordered_patch_items',[])}: raise PatchAuthoringError('unconfirmed_patch_item')
    body={'schema':INTAKE_SCHEMA,'session_id':session_id,'iteration_reference':dict(iteration_reference),'patch_candidate_reference':_ref(patch_candidate),'patch_validation_reference':_ref(patch_validation),'human_patch_review_reference':_ref(human_patch_review),'repair_strategy_reference':_ref(repair_strategy),'impact_analysis_reference':_ref(impact_analysis),'repository_identity':dict(repository_identity),'confirmed_scope':list(confirmed_scope),'confirmed_patch_items':sorted(confirmed_ids),'confirmed_paths':sorted(confirmed_paths),'confirmed_test_targets':list(human_patch_review.get('confirmed_test_targets') or []),'authoring_constraints':{'maximum_files':MAX_FILES,'maximum_file_bytes':MAX_FILE_BYTES,'maximum_total_bytes':MAX_TOTAL_BYTES,'utf8_text_only':True,'repository_mutation':False},'authority':AUTHORITY}
    return canon(body,'authoring_intake_fingerprint','authoring_intake_id','engineering-patch-authoring-intake-')

def snapshot_patch_sources(intake:Mapping[str,Any],patch_candidate:Mapping[str,Any],*,workspace_root:str|Path)->dict[str,Any]:
    paths=list(intake.get('confirmed_paths') or [])
    if len(paths)>MAX_FILES: raise PatchAuthoringError('maximum_file_count_exceeded')
    rows=[]; total=0
    for path in paths:
        try: p=safe_path(workspace_root,path)
        except Exception as exc:
            if getattr(exc,'code',str(exc))=='binary_file_rejected': raise PatchAuthoringError('binary_source_file') from exc
            raise
        item=next((x for x in patch_candidate.get('ordered_patch_items',[]) if x.get('path')==path),None)
        if not item: raise PatchAuthoringError('unconfirmed_patch_item')
        if not p.is_file(): raise PatchAuthoringError('unknown_edit_path')
        raw=p.read_bytes(); total+=len(raw)
        if len(raw)>MAX_FILE_BYTES or total>MAX_TOTAL_BYTES: raise PatchAuthoringError('oversized_source_file')
        if b'\x00' in raw: raise PatchAuthoringError('binary_source_file')
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError as exc: raise PatchAuthoringError('binary_source_file') from exc
        newline='crlf' if '\r\n' in text else 'lf' if '\n' in text else 'none'
        material={'path':path,'file_role':item.get('file_role') or classify_role(path),'file_sha256':hashlib.sha256(raw).hexdigest(),'file_size':len(raw),'encoding':'utf-8','newline_style':newline,'repository_relative_path':path,'bounded_source_reference':{'text':text,'byte_count':len(raw)}}
        rows.append(canon(material,'source_snapshot_fingerprint','source_snapshot_id','engineering-source-snapshot-'))
    return canon({'schema':SNAPSHOT_SCHEMA,'session_id':intake.get('session_id'),'authoring_intake_reference':_ref(intake),'repository_identity':intake.get('repository_identity'),'sources':rows,'bounded_file_count':len(rows),'bounded_total_bytes':total,'authority':AUTHORITY},'source_set_fingerprint','source_set_id','engineering-source-set-')

def _candidate_content(kind:str,source:str,definition:Mapping[str,Any])->str:
    if kind=='replace_exact_text':
        old=str(definition.get('old_text',''))
        if not old or source.count(old)!=1: raise PatchAuthoringError('exact_match_not_unique')
        return source.replace(old,str(definition.get('new_text','')),1)
    if kind=='replace_file_content': return str(definition.get('candidate_content',''))
    if kind=='append_text': return source+str(definition.get('append_text',''))
    if kind=='remove_exact_text':
        old=str(definition.get('old_text',''))
        if not old or source.count(old)!=1: raise PatchAuthoringError('exact_match_not_unique')
        return source.replace(old,'',1)
    if kind=='create_text_file': return str(definition.get('candidate_content',''))
    raise PatchAuthoringError('unsupported_edit_kind')

def author_file_edits(intake:Mapping[str,Any],patch_candidate:Mapping[str,Any],source_set:Mapping[str,Any],definitions:Sequence[Mapping[str,Any]],*,previous_candidate_reference:Mapping[str,Any]|None=None)->tuple[dict[str,Any],dict[str,Any]]:
    sources={x['path']:x for x in source_set.get('sources',[])}; patch_items={x['patch_item_id']:x for x in patch_candidate.get('ordered_patch_items',[])}; edits=[]
    for definition in definitions:
        if PROHIBITED_KEYS.intersection(definition): raise PatchAuthoringError('authority_payload_rejection')
        item=patch_items.get(definition.get('patch_item_id')); path=definition.get('path')
        if not item or item.get('path')!=path or item.get('patch_item_id') not in intake.get('confirmed_patch_items',[]): raise PatchAuthoringError('unconfirmed_patch_item')
        if path not in intake.get('confirmed_paths',[]): raise PatchAuthoringError('scope_expansion_required')
        kind=definition.get('candidate_edit_kind'); source=(sources.get(path) or {}).get('bounded_source_reference',{}).get('text','')
        content=_candidate_content(kind,source,definition)
        if len(content.encode('utf-8'))>MAX_FILE_BYTES: raise PatchAuthoringError('oversized_candidate_content')
        lowered=content.lower()
        if any(token in lowered for token in PROHIBITED_CONTENT): raise PatchAuthoringError('authority_payload_rejection')
        diff=''.join(difflib.unified_diff(source.splitlines(True),content.splitlines(True),fromfile='a/'+path,tofile='b/'+path,lineterm='\n'))
        material={'schema':EDIT_SCHEMA,'session_id':intake.get('session_id'),'authoring_intake_reference':_ref(intake),'patch_candidate_reference':_ref(patch_candidate),'patch_item_reference':{'patch_item_id':item['patch_item_id']},'path':path,'file_role':item.get('file_role'),'source_snapshot_reference':_ref(sources.get(path) or {}),'target_symbols':list(item.get('related_symbols') or []),'edit_intent':item.get('change_intent'),'candidate_edit_kind':kind,'candidate_content':content,'candidate_diff':diff,'acceptance_criteria':list(item.get('related_acceptance_criteria') or []),'test_impact':item.get('expected_test_impact'),'risk':item.get('risk_level'),'limitations':['candidate only; repository unchanged','human authored input required'],'previous_candidate_reference':dict(previous_candidate_reference or {}),'authority':AUTHORITY}
        edits.append(canon(material,'file_edit_fingerprint','file_edit_id','engineering-file-edit-'))
    edits=sorted(edits,key=lambda x:x['path']); file_edits=[x for x in edits if x.get('file_role')!='test']; test_edits=[x for x in edits if x.get('file_role')=='test']
    for edit in test_edits:
        if not edit['path'].startswith('tests/') or edit['path'] not in [str(x).split('::')[0] for x in intake.get('confirmed_test_targets',[])]: raise PatchAuthoringError('unconfirmed_test_target')
    return canon({'schema':'zero.engineering.file_edit_candidate_set.v1','authoring_intake_reference':_ref(intake),'edits':file_edits,'authority':AUTHORITY},'edit_set_fingerprint','edit_set_id','engineering-file-edit-set-'),canon({'schema':'zero.engineering.test_edit_candidate_set.v1','authoring_intake_reference':_ref(intake),'edits':test_edits,'authority':AUTHORITY},'edit_set_fingerprint','edit_set_id','engineering-test-edit-set-')

def build_candidate_diff(intake:Mapping[str,Any],source_set:Mapping[str,Any],file_edits:Mapping[str,Any],test_edits:Mapping[str,Any],*,previous_candidate_reference:Mapping[str,Any]|None=None)->dict[str,Any]:
    edits=sorted(list(file_edits.get('edits') or [])+list(test_edits.get('edits') or []),key=lambda x:x['path']); unified=''.join(x.get('candidate_diff','') for x in edits)
    added=sum(1 for line in unified.splitlines() if line.startswith('+') and not line.startswith('+++')); removed=sum(1 for line in unified.splitlines() if line.startswith('-') and not line.startswith('---')); hunks=sum(1 for line in unified.splitlines() if line.startswith('@@'))
    body={'schema':DIFF_SCHEMA,'session_id':intake.get('session_id'),'authoring_intake_reference':_ref(intake),'source_snapshot_reference':_ref(source_set),'file_edit_candidate_references':[_ref(x) for x in edits],'ordered_paths':[x['path'] for x in edits],'unified_diff':unified,'diff_summary':{'file_count':len(edits),'candidate_only':True,'repository_modified':False},'added_lines':added,'removed_lines':removed,'changed_hunks':hunks,'scope_validation':{'confirmed_paths':list(intake.get('confirmed_paths') or []),'within_scope':all(x['path'] in intake.get('confirmed_paths',[]) for x in edits)},'previous_candidate_reference':dict(previous_candidate_reference or {}),'authority':AUTHORITY}
    return canon(body,'candidate_diff_fingerprint','candidate_diff_id','engineering-candidate-diff-')

def validate_authored_patch(diff:Mapping[str,Any],*,intake:Mapping[str,Any]|None=None,patch_candidate:Mapping[str,Any]|None=None,human_patch_review:Mapping[str,Any]|None=None,source_set:Mapping[str,Any]|None=None,file_edits:Mapping[str,Any]|None=None,test_edits:Mapping[str,Any]|None=None,workspace_root:str|Path='.',repository_identity:Mapping[str,Any]|None=None,session_id:str|None=None,iteration_reference:Mapping[str,Any]|None=None)->dict[str,Any]:
    errors=[]; edits=list((file_edits or {}).get('edits') or [])+list((test_edits or {}).get('edits') or [])
    if not human_patch_review: errors.append('missing_patch_review')
    elif human_patch_review.get('decision')!='confirmed': errors.append('patch_review_not_confirmed')
    if intake and human_patch_review and intake.get('human_patch_review_reference')!=_ref(human_patch_review): errors.append('stale_patch_candidate')
    if not source_set: errors.append('missing_source_snapshot')
    if intake and source_set and source_set.get('authoring_intake_reference')!=_ref(intake): errors.append('source_snapshot_unresolved')
    if repository_identity is not None and intake and dict(intake.get('repository_identity') or {})!=dict(repository_identity): errors.append('wrong_repository_identity')
    if session_id and (not intake or intake.get('session_id')!=session_id or diff.get('session_id')!=session_id): errors.append('session_mismatch')
    if iteration_reference is not None and intake and intake.get('iteration_reference')!=dict(iteration_reference): errors.append('iteration_mismatch')
    try:
        current=snapshot_patch_sources(intake or {},patch_candidate or {},workspace_root=workspace_root)
        if source_set and current.get('source_set_fingerprint')!=source_set.get('source_set_fingerprint'): errors.extend(['source_fingerprint_mismatch','workspace_drift'])
    except Exception: errors.append('workspace_drift')
    confirmed_paths=set((intake or {}).get('confirmed_paths') or []); confirmed_items=set((intake or {}).get('confirmed_patch_items') or []); confirmed_tests={str(x).split('::')[0] for x in (intake or {}).get('confirmed_test_targets') or []}
    for edit in edits:
        if edit.get('path') not in confirmed_paths: errors.append('scope_expansion_required')
        if edit.get('patch_item_reference',{}).get('patch_item_id') not in confirmed_items: errors.append('unconfirmed_patch_item')
        if edit.get('file_role')=='test' and edit.get('path') not in confirmed_tests: errors.append('unconfirmed_test_target')
        if edit.get('candidate_edit_kind') not in EDIT_KINDS: errors.append('unsupported_edit_kind')
        if not edit.get('acceptance_criteria'): errors.append('missing_acceptance_mapping')
        if not edit.get('test_impact'): errors.append('missing_test_impact')
        if PROHIBITED_KEYS.intersection(edit) or any(edit.get('authority',{}).get(k) for k in AUTHORITY): errors.append('authority_payload_rejection')
    try:
        rebuilt=build_candidate_diff(intake or {},source_set or {},file_edits or {},test_edits or {},previous_candidate_reference=diff.get('previous_candidate_reference'))
        if rebuilt!=diff: errors.append('candidate_diff_mismatch')
    except Exception: errors.append('candidate_diff_mismatch')
    if not (diff.get('scope_validation') or {}).get('within_scope'): errors.append('scope_expansion_required')
    if PROHIBITED_KEYS.intersection(diff) or any(diff.get('authority',{}).get(k) for k in AUTHORITY): errors.append('authority_payload_rejection')
    if 'change_package' in diff or 'change_package_reference' in diff: errors.append('change_package_payload_rejection')
    body={'schema':VALIDATION_SCHEMA,'candidate_diff_reference':_ref(diff),'valid':not errors,'validation_status':'valid' if not errors else 'invalid','reason_codes':sorted(set(errors)),'workspace_drift_status':'detected' if 'workspace_drift' in errors else 'not_detected','authority':AUTHORITY}
    return canon(body,'authoring_validation_fingerprint','authoring_validation_id','engineering-authoring-validation-')

def review_authored_patch(diff:Mapping[str,Any],file_edits:Mapping[str,Any],test_edits:Mapping[str,Any],validation:Mapping[str,Any],review:Mapping[str,Any])->dict[str,Any]:
    if not review.get('human_actor'): raise PatchAuthoringError('human_actor_required')
    if review.get('candidate_diff_reference')!=_ref(diff): raise PatchAuthoringError('stale_candidate_diff')
    decision=review.get('decision')
    if decision not in {'confirmed','rejected','requires_revision'}: raise PatchAuthoringError('invalid_authored_patch_review_decision')
    if decision=='confirmed' and validation.get('validation_status')!='valid': raise PatchAuthoringError('invalid_authored_patch_candidate')
    refs=[_ref(x) for x in list(file_edits.get('edits') or [])+list(test_edits.get('edits') or [])]
    body={'schema':REVIEW_SCHEMA,'candidate_diff_reference':_ref(diff),'file_edit_candidate_references':refs,'human_actor':review['human_actor'],'decision':decision,'confirmed_paths':list(review.get('confirmed_paths') or []),'confirmed_edit_ids':list(review.get('confirmed_edit_ids') or []),'confirmed_test_edits':list(review.get('confirmed_test_edits') or []),'risk_acknowledgements':list(review.get('risk_acknowledgements') or []),'source_snapshot_acknowledgement':bool(review.get('source_snapshot_acknowledgement')),'scope_acknowledgement':bool(review.get('scope_acknowledgement')),'notes':review.get('notes',''),'not_approval':True,'not_authorization':True,'not_execution_permission':True,'not_change_package_admission':True,'authority':AUTHORITY}
    return canon(body,'authored_patch_review_fingerprint','authored_patch_review_id','engineering-authored-patch-review-')

def inspect_patch_authoring_state(bundle:Mapping[str,Any])->dict[str,Any]:
    get=lambda key:bundle.get(STORE_FILES[key]) or {}; files=get('file_edits').get('edits',[]); tests=get('test_edits').get('edits',[])
    return {'patch_authoring_intake_status':'created' if get('intake') else 'missing','source_snapshot_status':'created' if get('snapshots') else 'missing','file_edit_candidate_count':len(files),'test_edit_candidate_count':len(tests),'candidate_diff_status':'created' if get('diff') else 'missing','authoring_validation_status':get('validation').get('validation_status','not_started'),'authored_patch_review_status':get('review').get('decision','not_started'),'workspace_drift_status':get('validation').get('workspace_drift_status','unknown'),'scope_expansion_status':'required' if 'scope_expansion_required' in get('validation').get('reason_codes',[]) else 'not_required','next_governed_action':resume_patch_authoring_state(bundle)['decision']}

def resume_patch_authoring_state(bundle:Mapping[str,Any])->dict[str,Any]:
    if not bundle.get('repair/patch-review.json'): decision='requires_human_patch_review'
    elif not bundle.get(STORE_FILES['intake']): decision='requires_patch_authoring_intake'
    elif not bundle.get(STORE_FILES['snapshots']): decision='requires_source_snapshot'
    elif not bundle.get(STORE_FILES['diff']): decision='requires_human_authored_edits'
    elif not bundle.get(STORE_FILES['validation']): decision='requires_authoring_validation'
    elif not bundle.get(STORE_FILES['review']): decision='requires_human_authored_patch_review'
    else: decision='human_authored_patch_review_recorded'
    return {'schema':'zero.engineering.patch_authoring_resume.v1','decision':decision,'will_author_edits':False,'will_apply_patch':False,'will_modify_repository':False,'will_create_change_package':False,'will_approve':False,'will_authorize':False,'will_execute':False,'will_retry':False,'will_complete':False}
