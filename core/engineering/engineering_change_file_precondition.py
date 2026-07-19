from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_file_precondition(payload:dict[str,Any], evidence:dict[str,Any]|None=None)->dict[str,Any]:
 rs=require_mapping(payload); cond=payload.get('conditions',{}); ev=evidence or {}; kind=ev.get('observed_path_kind')
 if payload.get('expected_workspace_id') and ev.get('workspace_id') and payload.get('expected_workspace_id')!=ev.get('workspace_id'): rs.append('workspace_mismatch')
 if payload.get('expected_workspace_root_fingerprint') and ev.get('workspace_root_fingerprint') and payload.get('expected_workspace_root_fingerprint')!=ev.get('workspace_root_fingerprint'): rs.append('workspace_root_fingerprint_mismatch')
 if cond.get('expected_missing') and kind not in (None,'missing'): rs.append('expected_missing_not_satisfied')
 if cond.get('expected_regular_file') and kind not in ('file','regular_file'): rs.append('expected_regular_file_not_satisfied')
 if cond.get('expected_directory') and kind!='directory': rs.append('expected_directory_not_satisfied')
 if cond.get('expected_sha256') and ev.get('observed_content_sha256')!=cond.get('expected_sha256'): rs.append('expected_sha256_mismatch')
 if cond.get('expected_size_bytes') is not None and ev.get('observed_size')!=cond.get('expected_size_bytes'): rs.append('expected_size_mismatch')
 body={'relative_path':payload.get('relative_path'),'conditions':cond,'workspace_evidence_id':ev.get('workspace_evidence_id'),'workspace_evidence_fingerprint':ev.get('fingerprint'),'status':'satisfied_by_evidence' if not rs else 'not_satisfied_by_evidence','reason_codes':reasons(rs)}
 return artifact('cpre',SCHEMAS['file_precondition'],body,'precondition_id')
