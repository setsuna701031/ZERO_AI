from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def bind_workspace_evidence(payload:dict[str,Any])->dict[str,Any]:
 closure=payload.get('closure',{}); ver=payload.get('verification',{}); result=payload.get('result',{}); obs=payload.get('observation_output',payload.get('output',{})); root=payload.get('root_admission',{}); scope=payload.get('read_scope',{}); path=payload.get('path_resolution',{})
 rs=[]
 if closure.get('schema')!='zero.engineering.runtime_workspace_execution_closure.v1': rs.append('closure_schema_invalid')
 if ver.get('schema')!='zero.engineering.runtime_workspace_execution_verification.v1': rs.append('verification_schema_invalid')
 if closure.get('closure_status')!='closed': rs.append('workspace_not_closed')
 if ver.get('verification_status')!='verified': rs.append('workspace_not_verified')
 if result.get('result_status') not in ('succeeded','success'): rs.append('observation_not_succeeded')
 if result.get('workspace_id')!=root.get('workspace_id'): rs.append('workspace_mismatch')
 if result.get('workspace_root_fingerprint') and root.get('workspace_root_fingerprint') and result.get('workspace_root_fingerprint')!=root.get('workspace_root_fingerprint'): rs.append('workspace_root_fingerprint_mismatch')
 if result.get('filesystem_mutation_performed') is not False and result.get('mutation_invariant')!='filesystem_mutation_performed_false': rs.append('mutation_invariant_invalid')
 if path.get('path_resolution_status') not in (None,'resolved','admitted'): rs.append('path_resolution_invalid')
 body={'workspace_execution_closure_id':closure.get('closure_id'),'workspace_execution_closure_fingerprint':closure.get('fingerprint'),'workspace_verification_id':ver.get('verification_id'),'workspace_verification_fingerprint':ver.get('fingerprint'),'workspace_result_id':result.get('result_id'),'workspace_result_fingerprint':result.get('fingerprint'),'observation_output_id':obs.get('observation_output_id',obs.get('output_id')),'observation_output_fingerprint':obs.get('fingerprint'),'workspace_id':result.get('workspace_id',root.get('workspace_id')),'workspace_root_fingerprint':root.get('workspace_root_fingerprint',result.get('workspace_root_fingerprint')),'read_scope_id':scope.get('read_scope_id'),'read_scope_fingerprint':scope.get('fingerprint'),'path_resolution_id':path.get('path_resolution_id'),'path_resolution_fingerprint':path.get('fingerprint'),'observed_relative_path':result.get('relative_path',obs.get('relative_path')),'observed_path_kind':result.get('path_kind',obs.get('path_kind')),'observed_size':result.get('size_bytes',obs.get('size_bytes')),'observed_content_sha256':result.get('content_sha256',obs.get('content_sha256')),'upstream_execution_session_id':result.get('execution_session_id'),'adapter_id':result.get('adapter_id'),'adapter_version':result.get('adapter_version'),'operation':result.get('operation'),'mutation_invariant':'filesystem_mutation_performed_false','external_effect_invariant':'external_effect_performed_false','status':'bound' if not rs else 'rejected','reason_codes':reasons(rs)}
 return artifact('cwev',SCHEMAS['workspace_evidence'],body,'workspace_evidence_id')
