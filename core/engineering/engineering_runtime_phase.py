from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_phase(session_id:str,phase:str="request_received",sequence:int=1)->dict[str,Any]:
    rs=[] if phase in PHASES and type(sequence) is int and sequence>=1 else ["phase_invalid"]
    return artifact("runtime_phase",{"session_id":session_id,"phase":phase,"sequence":sequence,"status":"valid" if not rs else "invalid","reason_codes":rs},"phase_id")
def transition_phase(current:Mapping[str,Any],next_phase:str)->dict[str,Any]:
    try: old=PHASES.index(current.get("phase")); new=PHASES.index(next_phase)
    except ValueError: return build_engineering_runtime_phase(str(current.get("session_id")),"request_received",int(current.get("sequence",0))+1)|{"status":"invalid","reason_codes":["phase_invalid"]}
    if new!=old+1 or (next_phase=="execution_started" and current.get("execution_started")): return artifact("runtime_phase",{"session_id":current.get("session_id"),"phase":current.get("phase"),"sequence":current.get("sequence"),"status":"invalid","reason_codes":["invalid_phase_transition"]},"phase_id")
    return build_engineering_runtime_phase(str(current.get("session_id")),next_phase,int(current.get("sequence",0))+1)
