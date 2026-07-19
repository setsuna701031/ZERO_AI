from tests.runtime_adapter_activation_authorization_fixtures import request
from core.engineering.engineering_runtime_adapter_activation_authorization_request import validate_runtime_adapter_activation_authorization_request, inspect_runtime_adapter_activation_authorization_request
def invalid(**kw):
 r=request(**kw); return validate_runtime_adapter_activation_authorization_request(r).errors
def test_valid_request_and_inspect():
 r=request(); assert validate_runtime_adapter_activation_authorization_request(r).valid; assert inspect_runtime_adapter_activation_authorization_request(r)['valid']
def test_request_rejections():
 cases=[({'activation_eligibility_status':'ineligible'},'eligibility_not_eligible'),({'activation_eligibility_closure_status':'open'},'eligibility_closure_not_closed'),({'activation_eligibility_handoff_id':'bad'},'identity_mismatch'),({'activation_eligibility_handoff_fingerprint':'bad'},'identity_mismatch'),({'activation_eligibility_id':'bad'},'identity_mismatch'),({'activation_eligibility_fingerprint':'bad'},'identity_mismatch'),({'activation_eligibility_closure_id':'bad'},'identity_mismatch'),({'activation_eligibility_closure_fingerprint':'bad'},'identity_mismatch'),({'activation_eligibility_request_id':'bad'},'identity_mismatch'),({'activation_eligibility_policy_id':'bad'},'identity_mismatch'),({'activation_constraint_profile_id':'bad'},'identity_mismatch'),({'activation_eligibility_evaluation_id':'bad'},'identity_mismatch'),({'preparation_review_id':'bad'},'identity_mismatch'),({'preparation_id':'bad'},'identity_mismatch'),({'invocation_descriptor_id':'bad'},'identity_mismatch'),({'runtime_adapter_admission_id':'bad'},'identity_mismatch'),({'adapter_id':''},'identity_mismatch'),({'adapter_version':''},'identity_mismatch'),({'requested_authorized_scope':{'operations':['write']}},'scope_expansion'),({'requested_authorized_scope':'*'},'wildcard_scope'),({'requested_authorized_scope':'global'},'wildcard_scope'),({'requested_authorized_scope':'unrestricted'},'wildcard_scope'),({'authorization_constraints':{}},'invalid_authorization_constraints'),({'authorization_context':{}},'malformed_authorization_context')]
 for kw,code in cases: assert code in invalid(**kw)
def test_resource_timeout_environment_authority_rejections():
 for rc in ({},{'cpu':0},{'cpu':-1},{'cpu':'x'}): assert 'unbounded_resources' in invalid(resource_constraints=rc)
 for tc in ({},{'seconds':0,'finite':True,'perpetual':False},{'seconds':-1,'finite':True,'perpetual':False},{'seconds':float('inf'),'finite':True,'perpetual':False},{'seconds':1,'finite':True,'perpetual':True}): assert 'invalid_timeout' in invalid(timeout_constraints=tc)
 assert 'invalid_environment_constraints' in invalid(environment_constraints={})
 base=request()['authority_constraints']
 for key,val in [('non_transferable',False),('non_reusable',False),('scope_bound',False),('perpetual',True),('passive',False),('consumed',True),('closed',True),('unrestricted',True)]:
  a=dict(base); a[key]=val; assert 'unbounded_authority' in invalid(authority_constraints=a)
 a=dict(base); a['scope']={'operations':['write']}; assert 'unbounded_authority' in invalid(authority_constraints=a)
def test_payload_rejections():
 for k in ['command','shell','script','source_code','executable','binary','module_path','callback','entrypoint','patch','activation_command','credentials','api_key','private_key','bearer','environment_secrets','activation_token','token_value','token_material','authorization_header']:
  assert 'executable_payload' in invalid(authorization_context={'purpose':'authorization',k:'x'})
