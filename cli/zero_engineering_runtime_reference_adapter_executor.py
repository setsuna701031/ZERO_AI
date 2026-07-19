from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_intake_common import canonical_json
from core.engineering.engineering_runtime_reference_adapters import default_reference_adapter_registry
from core.engineering.engineering_runtime_reference_adapter_protocol import build_reference_adapter_descriptor
from core.engineering.engineering_runtime_adapter_execution_submission import build_execution_submission
from core.engineering.engineering_runtime_adapter_execution_preflight import build_execution_preflight
from core.engineering.engineering_runtime_adapter_execution_cancellation import build_execution_cancellation
from core.engineering.engineering_runtime_adapter_controlled_executor import execute_controlled_reference_adapter
from core.engineering.engineering_runtime_adapter_execution_output import build_execution_output, validate_canonical_payload
from core.engineering.engineering_runtime_adapter_execution_failure import build_execution_failure
from core.engineering.engineering_runtime_adapter_execution_result import build_execution_result
from core.engineering.engineering_runtime_adapter_execution_verification import verify_execution_result
from core.engineering.engineering_runtime_adapter_execution_evidence import build_execution_evidence
from core.engineering.engineering_runtime_adapter_execution_closure import build_execution_closure
ACTIONS={'descriptor','registry','submission','preflight','cancellation','execute','output','result','verify','evidence','closure','validate','inspect','pipeline'}
def _read(p): return json.loads(Path(p).read_text(encoding='utf-8') if p else sys.stdin.read() or '{}')
def _emit(v): sys.stdout.write(canonical_json(v)+'\n')
def _err(code): _emit({'schema':'zero.engineering.runtime_reference_adapter_executor_cli_error.v1','status':'error','error_code':code}); return 1
def pipeline(data):
 reg=default_reference_adapter_registry(); sub=build_execution_submission(data['handoff'],data.get('closure',{}),data.get('input_payload'),data.get('input_contract_identifier','input.contract'),adapter_id=data.get('adapter_id'),adapter_version=data.get('adapter_version'),operation=data.get('operation'),approved_scope=data.get('approved_scope'),authority_constraints=data.get('authority_constraints'),expected_output_contract=data.get('expected_output_contract'))
 can=build_execution_cancellation(sub,data.get('cancel_requested',False)); pre=build_execution_preflight(sub,reg,can); ctrl=execute_controlled_reference_adapter(sub,pre,can,reg); desc=reg.descriptor(sub.get('adapter_id'),sub.get('adapter_version')) or {}; res=build_execution_result(sub,pre,desc,ctrl,can); ver=verify_execution_result(res,sub,pre,ctrl,reg); ev=build_execution_evidence(res,ver); clo=build_execution_closure(res,ver,ev)
 return {'submission':sub,'cancellation':can,'preflight':pre,'controlled_execution':ctrl,'result':res,'verification':ver,'evidence':ev,'closure':clo}
def main(argv=None):
 ap=argparse.ArgumentParser(); ap.add_argument('action',choices=sorted(ACTIONS)); ap.add_argument('--input'); ns=ap.parse_args(argv)
 try: data=_read(ns.input); reg=default_reference_adapter_registry(); a=ns.action
 except Exception: return _err('invalid_json_input')
 try:
  if a=='registry': out=reg.snapshot()
  elif a=='descriptor': out=build_reference_adapter_descriptor(reg.lookup(data.get('adapter_id','canonical_echo'),data.get('adapter_version','1.0')))
  elif a=='submission': out=build_execution_submission(data['handoff'],data.get('closure',{}),data.get('input_payload'),data.get('input_contract_identifier','input.contract'),adapter_id=data.get('adapter_id'),adapter_version=data.get('adapter_version'),operation=data.get('operation'),approved_scope=data.get('approved_scope'),authority_constraints=data.get('authority_constraints'),expected_output_contract=data.get('expected_output_contract'))
  elif a=='cancellation': out=build_execution_cancellation(data.get('submission',data),data.get('requested',False))
  elif a=='preflight': out=build_execution_preflight(data['submission'],reg,data.get('cancellation'))
  elif a=='execute': out=execute_controlled_reference_adapter(data['submission'],data['preflight'],data.get('cancellation',{}),reg)
  elif a=='output': out=build_execution_output(data.get('submission',{}),data.get('output'),data.get('expected_output_contract'))
  elif a=='result': out=build_execution_result(data['submission'],data['preflight'],data.get('descriptor',{}),data['controlled_execution'],data.get('cancellation',{}))
  elif a=='verify': out=verify_execution_result(data['result'],data['submission'],data['preflight'],data['controlled_execution'],reg)
  elif a=='evidence': out=build_execution_evidence(data['result'],data['verification'])
  elif a=='closure': out=build_execution_closure(data['result'],data['verification'],data.get('evidence',{}))
  elif a in {'validate','inspect'}: ok,errs,_=validate_canonical_payload(data); out={'valid':ok,'reason_codes':errs}
  else: out=pipeline(data)
  _emit(out); return 0
 except Exception: return _err('action_failed')
if __name__=='__main__': raise SystemExit(main())
