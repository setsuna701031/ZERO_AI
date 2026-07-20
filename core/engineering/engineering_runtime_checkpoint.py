from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_checkpoint(session,phase,previous=None,artifact_references=(),pause_requirements=(),execution_mode="disabled",result_status="in_progress"):
    seq=1 if previous is None else int(previous.get("sequence",0))+1
    return artifact("runtime_checkpoint",{"session_id":session.get("session_id"),"phase":phase.get("phase"),"previous_checkpoint_id":None if previous is None else previous.get("checkpoint_id"),"request_fingerprint":session.get("request_fingerprint"),"workspace_id":session.get("workspace_id"),"workspace_root_fingerprint":session.get("workspace_root_fingerprint"),"artifact_references":[ref(x) for x in artifact_references],"pause_requirements":list(pause_requirements),"execution_mode":execution_mode,"result_status":result_status,"sequence":seq},"checkpoint_id")
def validate_checkpoint_chain(items):
    rs=[]
    for i,x in enumerate(items):
        rs+=validate_artifact(x,SCHEMAS["runtime_checkpoint"])
        if x.get("sequence")!=i+1 or (i and x.get("previous_checkpoint_id")!=items[i-1].get("checkpoint_id")): rs.append("checkpoint_sequence_invalid")
    return reasons(rs)
