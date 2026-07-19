from core.engineering.engineering_runtime_adapter_activation_admission import *
from core.engineering.engineering_runtime_adapter_activation_preparation import *
from core.engineering.engineering_runtime_adapter_controlled_activation import *
from core.engineering.engineering_runtime_adapter_activation_token_consumption import *
from core.engineering.engineering_runtime_adapter_activation_result import *
from core.engineering.engineering_runtime_adapter_activation_verification import *
from core.engineering.engineering_runtime_adapter_activation_handoff import *
from core.engineering.engineering_runtime_adapter_activation_closure import *

def token_handoff(**kw):
 d={'token_handoff_id':'handoff-1','fingerprint':'fp-handoff','token_id':'token-1','token_fingerprint':'fp-token','token_issuance_id':'issue-1','token_verification_id':'verify-token-1','token_verification_fingerprint':'fp-verify','token_authorization_id':'tokauth-1','activation_authorization_handoff_id':'authhandoff-1','activation_authorization_id':'auth-1','adapter_id':'adapter.alpha','adapter_version':'1.0','execution_session_id':'session-1','invocation_descriptor_id':'descriptor-1','activation_scope':{'adapter':['invoke']},'max_uses':1,'current_uses':0,'authority_reference':'authority-1','authority_constraints':{'valid':True,'consumed':False,'passive':True,'scope':{'adapter':['invoke']}},'activation_constraints':{'passive':True},'eligible_for_adapter_activation_admission':True,'activation_authorized':True,'token_issued':True,'token_verified':True,'token_consumed':False,'token_material_present':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False,'mutation_performed':False,'token_state':'issued_unconsumed'}; d.update(kw); return d

def pipeline(**handoff_overrides):
 h=token_handoff(**handoff_overrides); ar=build_runtime_adapter_activation_admission_request(h); ap=build_default_runtime_adapter_activation_admission_policy(); ad=build_runtime_adapter_activation_admission(ar,ap,h); pp=build_default_runtime_adapter_activation_preparation_policy(); pr=build_runtime_adapter_activation_preparation(ad,pp); ca=build_runtime_adapter_controlled_activation(pr,ad); tc=build_runtime_adapter_activation_token_consumption(ca); rs=build_runtime_adapter_activation_result(ca,tc); vf=verify_runtime_adapter_activation_boundary(ad,pr,ca,tc,rs); ho=build_runtime_adapter_activation_handoff(rs,vf,tc,ca); cl=build_runtime_adapter_activation_boundary_closure(ar,ap,ad,pp,pr,ca,tc,rs,vf,ho); return locals()
