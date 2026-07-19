from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_proposed_content(payload:dict[str,Any], policy:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(payload)+contains_prohibited_payload(payload); text=payload.get('content')
 st,cr=validate_text_content(text,policy.get('maximum_content_bytes_per_file',1),policy.get('maximum_line_count',1),policy.get('maximum_line_length',1)); rs+=cr
 body={'content':text if isinstance(text,str) else None,'content_sha256':st.get('sha256'),'content_byte_count':st.get('byte_count',0),'line_count':st.get('line_count',0),'max_line_length':st.get('max_line_length',0),'metadata':payload.get('metadata',{}),'status':'accepted' if not rs else 'rejected','reason_codes':reasons(rs)}
 return artifact('ccnt',SCHEMAS['content'],body,'content_id')
