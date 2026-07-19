from tests.runtime_adapter_execution_integration_fixtures import pipeline as upstream_pipeline
from core.engineering.engineering_runtime_reference_adapters import default_reference_adapter_registry
from core.engineering.engineering_runtime_adapter_execution_integration_common import stable_artifact
from core.engineering.engineering_runtime_adapter_execution_submission import build_execution_submission
from core.engineering.engineering_runtime_adapter_execution_cancellation import build_execution_cancellation
from core.engineering.engineering_runtime_adapter_execution_preflight import build_execution_preflight
from core.engineering.engineering_runtime_adapter_controlled_executor import execute_controlled_reference_adapter
from core.engineering.engineering_runtime_adapter_execution_result import build_execution_result
from core.engineering.engineering_runtime_adapter_execution_verification import verify_execution_result
from core.engineering.engineering_runtime_adapter_execution_evidence import build_execution_evidence
from core.engineering.engineering_runtime_adapter_execution_closure import build_execution_closure

def handoff_for(adapter_id='canonical_echo', op='echo'):
 p=upstream_pipeline(); h=dict(p['hand']); h.update({'adapter_id':adapter_id,'adapter_version':'1.0','allowed_operation':{'operation_id':op,'declarative':True},'expected_output_contract':{'contract_id':'output.contract'},'approved_scope':['scope.alpha'],'authority_constraints':{'valid':True,'consumed':False,'passive':True,'scope':['scope.alpha']},'upstream_closure_fingerprint':p['close']['fingerprint']}); h=stable_artifact(h,'executor_handoff_id','xhd-'); return h,p['close']
def run_pipeline(payload={'x':1}, adapter_id='canonical_echo', op='echo', cancel=False):
 h,c=handoff_for(adapter_id,op); reg=default_reference_adapter_registry(); sub=build_execution_submission(h,c,payload,'input.contract'); can=build_execution_cancellation(sub,cancel); pre=build_execution_preflight(sub,reg,can); ctrl=execute_controlled_reference_adapter(sub,pre,can,reg); desc=reg.descriptor(sub['adapter_id'],sub['adapter_version']) or {}; res=build_execution_result(sub,pre,desc,ctrl,can); ver=verify_execution_result(res,sub,pre,ctrl,reg); ev=build_execution_evidence(res,ver); clo=build_execution_closure(res,ver,ev); return locals()
