from __future__ import annotations
from typing import Any
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_mutation_transaction_common import fingerprint

COMPATIBILITY_SCHEMA = "zero.engineering.task_artifact_adapter_compatibility.v1"
PHASES = ('analysis','candidate_selection','repair_plan','proposal','approval','authorization','authorized_scope','preparation','preparation_token','authorization_token','executor_handoff','execution_result','verification','closure')

def build_compatibility_report(registry=None) -> dict[str, Any]:
    reg = registry or default_registry()
    rows=[]; supported=set()
    for adapter in reg.list():
        d=adapter.descriptor
        supported.add(d.phase)
        rows.append({
            'phase': d.phase,
            'supported_schema': d.supported_schema,
            'adapter_id': d.adapter_id,
            'adapter_version': d.adapter_version,
            'validation_level': d.validation_level,
            'validator_available': True,
            'identity_extraction_available': bool(d.identity_field),
            'fingerprint_extraction_available': bool(d.fingerprint_field),
            'linkage_coverage': sorted(d.linkage_fields),
            'orchestration_readiness': 'ready' if d.validation_level!='structural_reference_only' else 'limited',
            'limitations': [] if d.validation_level!='structural_reference_only' else ['structural_reference_only'],
            'health_status': 'healthy',
        })
    for phase in PHASES:
        if phase not in supported:
            rows.append({'phase':phase,'supported_schema':None,'adapter_id':None,'adapter_version':None,'validation_level':'unsupported','validator_available':False,'identity_extraction_available':False,'fingerprint_extraction_available':False,'linkage_coverage':[],'orchestration_readiness':'unsupported','limitations':['no_registered_canonical_adapter'],'health_status':'unsupported'})
    rows=sorted(rows,key=lambda r:(r['phase'],str(r['supported_schema'])))
    body={'schema':COMPATIBILITY_SCHEMA,'adapters':rows,'supported_phase_count':sum(1 for r in rows if r['health_status']=='healthy'),'unsupported_phases':[r['phase'] for r in rows if r['health_status']=='unsupported']}
    body['report_fingerprint']=fingerprint(body)
    return body
