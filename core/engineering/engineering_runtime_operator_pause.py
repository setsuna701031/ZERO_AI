from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_operator_pause(proposal,approval_artifacts=()):
    arts=list(approval_artifacts); decision=next((x for x in arts if x.get("decision") in ("approved","partially_approved","rejected")),None)
    rs=[]
    if decision and decision.get("automated_decision") is not False: rs.append("automated_approval_rejected")
    if decision and not decision.get("operator_id"): rs.append("operator_identity_required")
    status="rejected" if decision and decision.get("decision")=="rejected" else ("satisfied" if decision and not rs else ("invalid" if rs else "awaiting_input"))
    return artifact("runtime_operator_pause",{"proposal_coordination_id":proposal.get("proposal_coordination_id"),"status":status,"required_input":{"decision_required":True,"operator_identity_required":True,"automated_decision_allowed":False},"artifact_references":[ref(x) for x in arts],"operator_identity_inferred":False,"reason_codes":reasons(rs)},"operator_pause_id")
