from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_change_diff(payload:dict[str,Any], policy:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(payload); typ=payload.get('operation_type'); blocks=[]
 before=payload.get('before_content',''); after=payload.get('after_content','')
 if typ in ('create_text_file','replace_text_file','delete_file'):
  bs=before.splitlines(); af=after.splitlines(); blocks=[{'old_start_line':1,'old_line_count':len(bs),'new_start_line':1,'new_line_count':len(af),'removed_lines':bs,'added_lines':af}]
  for line in bs+af:
   if len(line)>policy.get('maximum_line_length',1): rs.append('line_too_long')
 if len(blocks)>policy.get('maximum_diff_entries',1): rs.append('diff_entry_limit_exceeded')
 if typ not in OPERATION_TYPES: rs.append('unsupported_operation_type')
 if payload.get('after_sha256') and typ!='delete_file' and sha256_text(after)!=payload.get('after_sha256'): rs.append('after_content_mismatch')
 body={'operation_type':typ,'target_relative_path':payload.get('target_relative_path'),'before_sha256':sha256_text(before) if isinstance(before,str) else None,'after_sha256':sha256_text(after) if isinstance(after,str) else None,'before_line_count':len(before.splitlines()) if isinstance(before,str) else 0,'after_line_count':len(after.splitlines()) if isinstance(after,str) else 0,'change_blocks':blocks,'operation_record':{'source_relative_path':payload.get('source_relative_path'),'target_relative_path':payload.get('target_relative_path')} if typ in ('create_directory','rename_path') else {},'status':'accepted' if not rs else 'rejected','reason_codes':reasons(rs)}
 return artifact('cdf',SCHEMAS['diff'],body,'diff_id')
