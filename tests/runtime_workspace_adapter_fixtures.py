from pathlib import Path
from core.engineering.engineering_runtime_workspace_adapter_registry import default_workspace_adapter_registry
from core.engineering.engineering_runtime_workspace_root_admission import admit_workspace_root
from core.engineering.engineering_runtime_workspace_read_scope import create_read_scope
from core.engineering.engineering_runtime_workspace_execution_submission import build_workspace_execution_submission
from core.engineering.engineering_runtime_workspace_execution_preflight import build_workspace_execution_preflight
from core.engineering.engineering_runtime_workspace_controlled_executor import execute_workspace_adapter
from core.engineering.engineering_runtime_workspace_execution_result import build_workspace_execution_result
from core.engineering.engineering_runtime_workspace_execution_verification import verify_workspace_execution
from core.engineering.engineering_runtime_workspace_execution_evidence import build_workspace_execution_evidence
from core.engineering.engineering_runtime_workspace_execution_closure import close_workspace_execution

def make_workspace(tmp_path):
 (tmp_path/'a.txt').write_text('hello',encoding='utf-8')
 (tmp_path/'b.bin').write_bytes(b'\xff')
 (tmp_path/'dir').mkdir(); (tmp_path/'dir'/'z.txt').write_text('z',encoding='utf-8')
 return tmp_path

def run_pipeline(root, operation='workspace_exists', relative_path='', scope=None, params=None, cancel=False):
 reg=default_workspace_adapter_registry(); adm=admit_workspace_root(root,'ws'); scope=scope or create_read_scope(); sub=build_workspace_execution_submission({'executor_handoff_id':'h'},{'closure_id':'c'},adm,scope,operation,relative_path,params or {},cancellation_state={'cancelled':cancel})
 pre,path=build_workspace_execution_preflight(sub,reg,adm,scope); cex=execute_workspace_adapter(sub,pre,reg,adm,scope); res=build_workspace_execution_result(sub,pre,cex); ver=verify_workspace_execution(sub,pre,cex,res); evd=build_workspace_execution_evidence(sub,pre,cex,res,ver); cls=close_workspace_execution(res,ver,evd)
 return reg,adm,scope,sub,pre,path,cex,res,ver,evd,cls
