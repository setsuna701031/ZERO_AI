from copy import deepcopy
from tests.runtime_adapter_activation_authorization_fixtures import chain_auth
from core.engineering.engineering_runtime_adapter_activation_token_eligibility import build_runtime_adapter_activation_token_eligibility_request,evaluate_runtime_adapter_activation_token_eligibility
from core.engineering.engineering_runtime_adapter_activation_token_preparation import build_default_runtime_adapter_activation_token_preparation_policy,build_runtime_adapter_activation_token_preparation
from core.engineering.engineering_runtime_adapter_activation_token_review import build_runtime_adapter_activation_token_review_request,evaluate_runtime_adapter_activation_token_review
from core.engineering.engineering_runtime_adapter_activation_token_authorization import build_default_runtime_adapter_activation_token_authorization_policy,build_runtime_adapter_activation_token_authorization
from core.engineering.engineering_runtime_adapter_activation_token_issuance import build_runtime_adapter_activation_token_issuance
from core.engineering.engineering_runtime_adapter_activation_token_verification import verify_runtime_adapter_activation_token
from core.engineering.engineering_runtime_adapter_activation_token_handoff import build_runtime_adapter_activation_token_handoff
from core.engineering.engineering_runtime_adapter_activation_token_closure import build_runtime_adapter_activation_token_governance_closure
SCOPE={'operations':['observe']}
CONSTRAINTS={'non_transferable':True,'non_reusable':True,'scope_bound':True,'adapter_bound':True,'session_bound':True,'authorization_bound':True,'passive':True,'consumed':False,'restricted':True,'bearer':False,'credential':False,'secret':False,'executable':False,'perpetual':False,'max_uses':1,'scope':deepcopy(SCOPE)}
AUTHORITY={'valid':True,'consumed':False,'restricted':True,'passive':True,'execution_authority_consumed':False,'activation_authority_consumed':False,'mutation_authority_consumed':False,'scope':deepcopy(SCOPE)}
def eligibility_request(**overrides):
 *_,hand,clo=chain_auth(); r=build_runtime_adapter_activation_token_eligibility_request(hand,clo,overrides.pop('requested_token_scope',deepcopy(SCOPE)),overrides.pop('requested_max_uses',1),overrides.pop('token_constraints',deepcopy(CONSTRAINTS)),overrides.pop('authority_reference','authority:activation-token'),overrides.pop('authority_constraints',deepcopy(AUTHORITY)),overrides.pop('request_context',{'purpose':'token-governance'})); r.update(overrides); return r,hand,clo
def chain_token(req=None):
 if req is None: req,hand,clo=eligibility_request()
 else: hand=clo=None
 elig=evaluate_runtime_adapter_activation_token_eligibility(req,hand,clo); ppol=build_default_runtime_adapter_activation_token_preparation_policy(); prep=build_runtime_adapter_activation_token_preparation(req,elig,ppol); rr=build_runtime_adapter_activation_token_review_request(prep,elig); rev=evaluate_runtime_adapter_activation_token_review(rr,prep,elig); apol=build_default_runtime_adapter_activation_token_authorization_policy(); auth=build_runtime_adapter_activation_token_authorization(rr,rev,prep,elig,apol); iss=build_runtime_adapter_activation_token_issuance(auth,rr); ver=verify_runtime_adapter_activation_token(iss,auth); hof=build_runtime_adapter_activation_token_handoff(iss,ver); clo2=build_runtime_adapter_activation_token_governance_closure(req,elig,ppol,prep,rr,rev,apol,auth,iss,ver,hof); return req,elig,ppol,prep,rr,rev,apol,auth,iss,ver,hof,clo2
