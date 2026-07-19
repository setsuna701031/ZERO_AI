from core.engineering.engineering_runtime_adapter_preparation_request import build_runtime_adapter_preparation_request
from core.engineering.engineering_runtime_adapter_preparation_policy import build_default_runtime_adapter_preparation_policy
from core.engineering.engineering_runtime_adapter_preparation_eligibility import evaluate_runtime_adapter_preparation_eligibility
from core.engineering.engineering_runtime_adapter_invocation_descriptor import build_runtime_adapter_invocation_descriptor
from core.engineering.engineering_runtime_adapter_preparation import build_runtime_adapter_preparation
from core.engineering.engineering_runtime_adapter_preparation_closure import build_runtime_adapter_preparation_closure
from tests.runtime_adapter_admission_fixtures import pipeline
AUTH={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'restricted':True,'scope':{'files':['a']}}
def upstream():
 _req,_pol,_elig,adm,h,s,_a=pipeline(); return adm,h,s
def request(**kw):
 adm,h,s=upstream();
 return build_runtime_adapter_preparation_request(kw.get('admission',adm),kw.get('handoff',h),kw.get('session',s),kw.get('adapter','adapter.one'),kw.get('version','1.0.0'),kw.get('operation',{'operation_type':'observe','target':'repo'}),kw.get('scope',{'files':['a']}),kw.get('inputs',{'artifact_ref':'opaque-artifact'}),kw.get('output',{'format':'json','schema_ref':'opaque-schema'}),kw.get('resources',{'cpu_units':1,'memory_mb':128}),kw.get('environment',{'network':'disabled','filesystem':'read_only'}),kw.get('timeout',{'seconds':30,'finite':True,'perpetual':False}),kw.get('ref','opaque-authority-ref'),kw.get('auth',AUTH.copy())),adm,h,s
def pipeline2(**kw):
 req,adm,h,s=request(**kw); pol=build_default_runtime_adapter_preparation_policy(); elig=evaluate_runtime_adapter_preparation_eligibility(req,pol,adm,h,s); desc=build_runtime_adapter_invocation_descriptor(req,elig,adm); prep=build_runtime_adapter_preparation(req,pol,elig,desc); clo=build_runtime_adapter_preparation_closure(req,pol,elig,desc,prep); return req,pol,elig,desc,prep,clo,adm,h,s
