from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import norm_paths, norm_path, no_overlap, seal, short_text
from core.engineering.engineering_repair_candidate import CHANGE_KINDS
from core.engineering.engineering_repair_plan import EXPECTATION_TYPES

SCHEMA='zero.engineering.bootstrap_request.v1'
STATUSES=('requested','invalid','blocked')
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','test_execution':'not_granted','verification':'not_granted','git':'not_granted','shell':'not_granted','network':'not_granted'}
MANDATORY_PROHIBITED=('.git',)

def build_engineering_bootstrap_request(*, repository_identity:Any, repository_root_reference:Mapping[str,Any], requested_outcome:str, request_summary:str, target_scope:Any, prohibited_scope:Any=(), allowed_change_kinds:Any=('replace_file',), verification_expectations:Any=('file_exists',), constraints:Any=(), assumptions:Any=(), analysis_policy:Mapping[str,Any]|None=None, planning_policy:Mapping[str,Any]|None=None, bootstrap_status:str='requested')->Mapping[str,Any]:
    targets=norm_paths(target_scope)
    prohibited=sorted(dict.fromkeys([norm_path(p) for p in [*(prohibited_scope or []),'.git']]))
    if not no_overlap(targets, prohibited): raise ValueError('target_prohibited_overlap')
    kinds=sorted(dict.fromkeys(short_text(x,64) for x in allowed_change_kinds))
    exps=sorted(dict.fromkeys(short_text(x,96) for x in verification_expectations))
    body={'schema':SCHEMA,'repository_identity':repository_identity,'repository_root_reference':dict(repository_root_reference),'requested_outcome':short_text(requested_outcome,512),'request_summary':short_text(request_summary,640),'target_scope':targets,'prohibited_scope':prohibited,'allowed_change_kinds':kinds,'verification_expectations':exps,'constraints':sorted(short_text(x,256) for x in constraints),'assumptions':sorted(short_text(x,256) for x in assumptions),'analysis_policy':dict(analysis_policy or {'mode':'canonical_artifacts_only','minimum_evidence':1}),'planning_policy':dict(planning_policy or {'maximum_risk':'medium'}),'bootstrap_status':bootstrap_status,'status':bootstrap_status,'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    return seal(body,'bootstrap_request_id','engineering-bootstrap-request')
