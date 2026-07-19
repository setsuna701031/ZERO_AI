from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_change_operation(payload:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(payload)+contains_prohibited_payload(payload); typ=payload.get('operation_type')
 if typ not in OPERATION_TYPES: rs.append('unsupported_operation_type')
 body={'operation_type':typ,'source_relative_path':payload.get('source_relative_path'),'target_relative_path':payload.get('target_relative_path'),'target_admission_id':payload.get('target_admission_id'),'target_admission_fingerprint':payload.get('target_admission_fingerprint'),'precondition_id':payload.get('precondition_id'),'precondition_fingerprint':payload.get('precondition_fingerprint'),'proposed_content_id':payload.get('proposed_content_id'),'proposed_content_fingerprint':payload.get('proposed_content_fingerprint'),'expected_before_fingerprint':payload.get('expected_before_fingerprint'),'proposed_after_fingerprint':payload.get('proposed_after_fingerprint'),'mutation_performed':False,'patch_applied':False,'filesystem_write_performed':False,'status':'accepted' if not rs else 'rejected','reason_codes':reasons(rs)}
 return artifact('cop',SCHEMAS['operation'],body,'operation_id')
