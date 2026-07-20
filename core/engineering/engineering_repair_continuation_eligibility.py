from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import freeze, seal
SCHEMA='zero.engineering.repair_continuation_eligibility.v1'; MAXIMUM_CYCLES=3
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','verification':'not_granted','retry':'not_granted'}

def derive_cycle_number(task_history:Any)->int:
    cycles=[x for x in (task_history or []) if isinstance(x,Mapping) and x.get('schema')=='zero.engineering.repair_continuation_cycle.v1']
    return len(cycles)+1

def evaluate_repair_continuation_eligibility(*, failure_analysis:Mapping[str,Any], verification_result:Mapping[str,Any], runtime_continuation:Mapping[str,Any], task_state:Mapping[str,Any]|None=None, task_history:Any=None, maximum_cycles:int=MAXIMUM_CYCLES, material_repair_change:bool=True)->Mapping[str,Any]:
    cycle=derive_cycle_number(task_history if task_history is not None else (task_state or {}).get('continuation_cycles',[])); reasons=[]
    status='eligible'; eligible=True
    if verification_result.get('verification_status') not in ('failed','blocked','invalid','not_verified'): reasons.append('verification_not_failed_or_blocked')
    if failure_analysis.get('repairability') not in ('repairable','possibly_repairable'): reasons.append('failure_not_repairable')
    if not failure_analysis.get('evidence_references') or failure_analysis.get('repairability')=='insufficient_evidence': reasons.append('insufficient_evidence')
    if (task_state or {}).get('lifecycle_state') in ('completed','closed') or (task_state or {}).get('terminal') is True: reasons.append('task_terminal')
    if any(r in failure_analysis.get('reason_codes',[]) for r in ('scope_expansion_required','authority_expansion_required','critical_rollback_failure','manual_only')): reasons.append('blocked_condition')
    if not material_repair_change: reasons.append('no_material_repair_change')
    if cycle>maximum_cycles: reasons.append('cycle_limit_reached')
    if reasons:
        eligible=False; status='cycle_limit_reached' if 'cycle_limit_reached' in reasons else 'manual_intervention_required' if 'no_material_repair_change' in reasons else 'blocked'
    body={'schema':SCHEMA,'task_id':failure_analysis.get('task_id'),'execution_session_id':failure_analysis.get('execution_session_id'),'failure_analysis_identity':failure_analysis.get('failure_analysis_id'),'failure_analysis_fingerprint':failure_analysis.get('fingerprint'),'verification_result_identity':verification_result.get('verification_result_id'),'runtime_continuation_identity':runtime_continuation.get('runtime_continuation_id'),'eligible':eligible,'eligibility_status':status,'reason_codes':sorted(dict.fromkeys(reasons or ['repair_continuation_eligible'])),'cycle_number':cycle,'maximum_cycles':maximum_cycles,'remaining_cycles':max(0,maximum_cycles-cycle),'scope_preserved':eligible,'authority_preserved':eligible,'human_approval_required':True,'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    return seal(body,'repair_continuation_eligibility_id','engineering-repair-continuation-eligibility')
