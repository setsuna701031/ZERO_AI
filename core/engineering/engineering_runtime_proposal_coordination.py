from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def coordinate_engineering_runtime_proposal(analysis,proposal_artifacts=()):
    refs=[ref(x) for x in proposal_artifacts if isinstance(x,dict) and x.get("fingerprint")]
    rs=[]
    if analysis.get("status")!="coordinated": rs.append("analysis_not_coordinated")
    if not refs: rs.append("proposal_artifacts_required")
    return artifact("runtime_proposal_coordination",{"analysis_coordination_id":analysis.get("analysis_coordination_id"),"status":"proposed" if not rs else "blocked","artifact_references":refs,"operator_approval_inferred":False,"reason_codes":reasons(rs)},"proposal_coordination_id")
