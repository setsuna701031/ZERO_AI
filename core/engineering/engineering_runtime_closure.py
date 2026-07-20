from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def close_engineering_runtime(result,verification,evidence):
    r=result.get("status"); status="invalid" if verification.get("status")!="verified" else ({"awaiting_operator_approval":"awaiting_operator_approval","awaiting_mutation_authorization":"awaiting_mutation_authorization","rejected":"rejected","recovery_required":"recovery_required"}.get(r,"closed"))
    return artifact("runtime_closure",{"result_id":result.get("result_id"),"verification_id":verification.get("verification_id"),"evidence_id":evidence.get("evidence_id"),"status":status,"reason_codes":verification.get("reason_codes",[])},"closure_id")
