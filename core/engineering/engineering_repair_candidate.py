from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import MAX_TEXT, freeze, norm_path, norm_paths, seal, short_text
from core.engineering.engineering_mutation_transaction_common import fingerprint

SCHEMA='zero.engineering.repair_candidate.v1'
STATUSES=('selected','not_selected','blocked','invalid')
DEFECT_CLASSES=('contract_mismatch','test_failure','compile_failure','configuration_defect','documentation_defect','scope_defect','integration_defect','unknown_bounded_defect')
RISKS=('low','medium','high')
CHANGE_KINDS=('create_file','replace_file','delete_file','mixed')
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','verification':'not_granted'}

def _evidence(items: Any) -> list[dict[str, Any]]:
    out=[]
    if not isinstance(items,(list,tuple)) or not items: raise ValueError('empty_evidence')
    for e in items:
        if not isinstance(e, Mapping): raise ValueError('evidence_not_mapping')
        d={'evidence_id': short_text(e.get('evidence_id'),96), 'evidence_type': short_text(e.get('evidence_type'),64), 'source_artifact_identity': short_text(e.get('source_artifact_identity'),160), 'source_fingerprint': short_text(e.get('source_fingerprint'),80), 'bounded_summary': short_text(e.get('bounded_summary'),640)}
        if e.get('repository_relative_path') is not None: d['repository_relative_path']=norm_path(e.get('repository_relative_path'))
        if e.get('location') is not None: d['location']=short_text(e.get('location'),160)
        if e.get('confidence') is not None: d['confidence']=float(e.get('confidence'))
        out.append(d)
    return sorted(out, key=lambda x:x['evidence_id'])

def build_engineering_repair_candidate(*, task_id:str, repository_identity:str, analysis_identity:str, analysis_fingerprint:str, requested_outcome:str, defect_classification:str, defect_summary:str, evidence_references:Any, target_scope:Any, prohibited_scope:Any=(), affected_components:Any=(), estimated_change_kind:str='replace_file', risk_level:str='medium', confidence:float=1.0, selection_status:str='selected') -> Mapping[str, Any]:
    targets=norm_paths(target_scope); prohibited=sorted(dict.fromkeys(norm_path(p) for p in prohibited_scope)) if prohibited_scope else []
    comps=sorted(dict.fromkeys(short_text(c,160) for c in (affected_components or [])))
    ev=_evidence(evidence_references)
    body={'schema':SCHEMA,'task_id':short_text(task_id,160),'repository_identity':repository_identity,'analysis_identity':short_text(analysis_identity,200),'analysis_fingerprint':short_text(analysis_fingerprint,80),'requested_outcome':short_text(requested_outcome,MAX_TEXT),'defect_classification':defect_classification,'defect_summary':short_text(defect_summary,640),'evidence_references':ev,'target_scope':targets,'prohibited_scope':prohibited,'affected_components':comps,'estimated_change_kind':estimated_change_kind,'risk_level':risk_level,'confidence':float(confidence),'selection_status':selection_status,'status':selection_status,'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    return freeze(seal(body,'candidate_id','engineering-repair-candidate'))
