from __future__ import annotations
import math
from typing import Any, Mapping
from core.engineering.engineering_intake_common import canonical_json
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint, normalize_reasons
SCHEMA='zero.engineering.runtime_adapter_execution_output.v1'; MAX_DEPTH=16; MAX_ITEMS=512; MAX_STRING=4096; DEFAULT_MAX_BYTES=65536

def validate_canonical_payload(v:Any,*,max_bytes:int=DEFAULT_MAX_BYTES,max_depth:int=MAX_DEPTH,max_items:int=MAX_ITEMS,max_string:int=MAX_STRING)->tuple[bool,tuple[str,...],int]:
 seen=set(); count=0; e=[]
 def walk(x,d):
  nonlocal count
  if d>max_depth: e.append('excessive_nesting'); return
  if id(x) in seen and isinstance(x,(dict,list,tuple)): e.append('cyclic_payload'); return
  if isinstance(x,(dict,list,tuple)): seen.add(id(x))
  count+=1
  if count>max_items: e.append('excessive_item_count')
  if x is None or isinstance(x,bool) or (isinstance(x,int) and not isinstance(x,bool)): return
  if isinstance(x,float):
   if not math.isfinite(x): e.append('non_finite_number')
   return
  if isinstance(x,str):
   if len(x)>max_string: e.append('oversized_string')
   low=x.lower()
   if any(s in low for s in ('bearer ','private key','password=','secret=','api_key=','authorization:')): e.append('credential_bearing_content')
   return
  if isinstance(x,bytes) or isinstance(x,bytearray) or isinstance(x,memoryview): e.append('binary_payload'); return
  if callable(x): e.append('callable_payload'); return
  if isinstance(x,Mapping):
   for k,y in x.items():
    if not isinstance(k,str): e.append('non_string_key')
    walk(y,d+1)
   return
  if isinstance(x,(list,tuple)):
   for y in x: walk(y,d+1)
   return
  e.append('unsupported_payload_type')
 walk(v,0)
 try: b=len(canonical_json(v).encode('utf-8'))
 except Exception: b=max_bytes+1; e.append('noncanonical_json')
 if b>max_bytes: e.append('oversized_payload')
 return not e, tuple(normalize_reasons(e)), b

def build_execution_output(submission:Mapping[str,Any], output:Any, expected_output_contract:Any=None, max_output_bytes:int=DEFAULT_MAX_BYTES)->dict[str,Any]:
 ok,errs,b=validate_canonical_payload(output,max_bytes=max_output_bytes)
 body={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'adapter_id':submission.get('adapter_id'),'adapter_version':submission.get('adapter_version'),'operation':submission.get('allowed_operation'),'output_contract':expected_output_contract if expected_output_contract is not None else submission.get('expected_output_contract'),'output_valid':ok,'output_byte_count':b,'reason_codes':errs}
 if ok: body['canonical_output']=output; body['output_fingerprint']=canonical_fingerprint(output)
 body['fingerprint']=canonical_fingerprint(body); body['output_id']='out-'+body['fingerprint'][:24]; return body
