from copy import deepcopy
from tests.runtime_adapter_activation_eligibility_fixtures import chain
from core.engineering.engineering_runtime_adapter_activation_authorization_request import build_runtime_adapter_activation_authorization_request
from core.engineering.engineering_runtime_adapter_activation_authorization_policy import build_default_runtime_adapter_activation_authorization_policy
from core.engineering.engineering_runtime_adapter_activation_authorization_review import evaluate_runtime_adapter_activation_authorization_review
from core.engineering.engineering_runtime_adapter_activation_authorization import build_runtime_adapter_activation_authorization
from core.engineering.engineering_runtime_adapter_activation_authorization_handoff import build_runtime_adapter_activation_authorization_handoff
from core.engineering.engineering_runtime_adapter_activation_authorization_closure import build_runtime_adapter_activation_authorization_closure
SCOPE={'operations':['observe']}
def upstream(): return chain()
def request(**overrides):
 *_,ho,clo=chain(); r=build_runtime_adapter_activation_authorization_request(ho,clo,overrides.pop('requested_authorized_scope',deepcopy(SCOPE)),overrides.pop('authorization_constraints',{'passive':True,'deterministic':True,'executable':False,'mode':'authorization_only'}),overrides.pop('resource_constraints',{'cpu_units':1,'memory_mb':128}),overrides.pop('timeout_constraints',{'seconds':30,'finite':True,'perpetual':False}),overrides.pop('environment_constraints',{'network':'disabled','runtime':'passive'}),overrides.pop('authorization_context',{'purpose':'authorization'})); r.update(overrides); return r
def chain_auth(req=None):
 req=req or request(); pol=build_default_runtime_adapter_activation_authorization_policy(); rev=evaluate_runtime_adapter_activation_authorization_review(req,pol); auth=build_runtime_adapter_activation_authorization(req,pol,rev); hand=build_runtime_adapter_activation_authorization_handoff(auth); clo=build_runtime_adapter_activation_authorization_closure(req,pol,rev,auth,hand); return req,pol,rev,auth,hand,clo
