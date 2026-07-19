from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_workspace_adapter_protocol import build_workspace_adapter_descriptor
from core.engineering.engineering_runtime_workspace_adapter_registry import default_workspace_adapter_registry
from core.engineering.engineering_runtime_workspace_root_admission import admit_workspace_root
from core.engineering.engineering_runtime_workspace_read_scope import create_read_scope
from core.engineering.engineering_runtime_workspace_path_resolution import resolve_workspace_path
from core.engineering.engineering_runtime_workspace_execution_submission import build_workspace_execution_submission
from core.engineering.engineering_runtime_workspace_execution_preflight import build_workspace_execution_preflight
from core.engineering.engineering_runtime_workspace_controlled_executor import execute_workspace_adapter
from core.engineering.engineering_runtime_workspace_execution_result import build_workspace_execution_result
from core.engineering.engineering_runtime_workspace_execution_verification import verify_workspace_execution
from core.engineering.engineering_runtime_workspace_execution_evidence import build_workspace_execution_evidence
from core.engineering.engineering_runtime_workspace_execution_closure import close_workspace_execution

def emit(obj): print(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False))
def load_payload(s): return json.loads(s or '{}')
def pipeline(root,p):
 reg=default_workspace_adapter_registry(); adm=admit_workspace_root(root,p.get('workspace_id','workspace')); scope=create_read_scope(**p.get('read_scope',{})); sub=build_workspace_execution_submission(p.get('executor_handoff',{'executor_handoff_id':'trusted-handoff'}),p.get('integration_closure',{'closure_id':'trusted-closure'}),adm,scope,p.get('operation','workspace_exists'),p.get('relative_path',''),p.get('operation_parameters',{}),p.get('execution_session_id','workspace-session'),cancellation_state=p.get('cancellation_state'))
 pre,path=build_workspace_execution_preflight(sub,reg,adm,scope); cex=execute_workspace_adapter(sub,pre,reg,adm,scope); res=build_workspace_execution_result(sub,pre,cex); ver=verify_workspace_execution(sub,pre,cex,res); evd=build_workspace_execution_evidence(sub,pre,cex,res,ver); cls=close_workspace_execution(res,ver,evd)
 return {'descriptor':build_workspace_adapter_descriptor(),'registry':reg.snapshot(),'workspace_admission':dict(adm),'read_scope':scope,'path_resolution':path,'submission':sub,'preflight':pre,'execution':cex,'result':res,'verification':ver,'evidence':evd,'closure':cls}
def main(argv=None):
 ap=argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('--json',default='{}'); ap.add_argument('--workspace-root'); ns=ap.parse_args(argv)
 try:
  p=load_payload(ns.json); action=ns.action
  if action=='descriptor': obj=build_workspace_adapter_descriptor()
  elif action=='registry': obj=default_workspace_adapter_registry().snapshot()
  elif action=='workspace-admission': obj=dict(admit_workspace_root(ns.workspace_root,p.get('workspace_id','workspace')))
  elif action=='read-scope': obj=create_read_scope(**p)
  elif action in ('pipeline','validate','inspect','path-resolution','submission','preflight','execute','output','result','verify','evidence','closure'):
   full=pipeline(ns.workspace_root,p)
   mapping={'path-resolution':'path_resolution','execute':'execution','verify':'verification'}; key=mapping.get(action,action.replace('-','_'))
   obj=full if action in ('pipeline','validate') else (full['result'].get('output') if action=='output' else full[key])
  else: obj={'error':{'code':'unknown_action'}}
  emit(obj); return 0
 except Exception:
  emit({'error':{'code':'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
