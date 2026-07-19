from core.engineering.engineering_execution_admission import build_engineering_execution_admission
from core.engineering.engineering_execution_session import build_engineering_execution_session
from core.engineering.engineering_runtime_handoff import build_engineering_runtime_handoff
from core.engineering.engineering_runtime_adapter_admission_request import build_runtime_adapter_admission_request
from core.engineering.engineering_runtime_adapter_admission_policy import build_default_runtime_adapter_admission_policy
from core.engineering.engineering_runtime_adapter_admission_eligibility import evaluate_runtime_adapter_admission_eligibility
from core.engineering.engineering_runtime_adapter_admission import build_runtime_adapter_admission
AUTH={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'scope':{'files':['a']}}
def upstream():
 intake={'governed_execution_intake_id':'intake-1','fingerprint':'fp-i','status':'accepted','execution_preparation_closure_id':'prep','execution_preparation_closure_fingerprint':'fp-p','repository_identity':'repo','analyzed_revision':'rev','sealed_execution_scope':{'files':['a','b']},'execution_constraints':[]}
 adm=build_engineering_execution_admission(intake); sess=build_engineering_execution_session(adm,intake); hand=build_engineering_runtime_handoff(sess); return hand,sess,adm
def request(**kw):
 h,s,a=upstream(); return build_runtime_adapter_admission_request(kw.get('handoff',h),kw.get('session',s),kw.get('admission',a),kw.get('adapter','adapter.one'),kw.get('version','1.0.0'),kw.get('scope',{'files':['a']}),kw.get('ref','opaque-ref'),kw.get('auth',AUTH.copy())),h,s,a
def pipeline(**kw):
 req,h,s,a=request(**kw); pol=build_default_runtime_adapter_admission_policy(); elig=evaluate_runtime_adapter_admission_eligibility(req,h,s,a); adm=build_runtime_adapter_admission(req,elig,pol); return req,pol,elig,adm,h,s,a
