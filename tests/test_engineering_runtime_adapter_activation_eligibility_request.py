from tests.runtime_adapter_activation_eligibility_fixtures import request
from core.engineering.engineering_runtime_adapter_activation_eligibility_request import validate_runtime_adapter_activation_eligibility_request as val
def bad(field,value,code):
 r=request(); r[field]=value; res=val(r); assert not res.valid and code in res.errors
def test_valid_request_and_repeatable():
 r=request(); assert val(r).valid; assert request()==request()
def test_status_and_linkage_rejections():
 bad('preparation_review_status','rejected','review_not_approved'); bad('preparation_review_closure_status','open','review_closure_not_closed'); bad('preparation_review_handoff_id','x','identity_mismatch'); bad('preparation_review_handoff_fingerprint','x','identity_mismatch'); bad('preparation_review_id','x','identity_mismatch'); bad('preparation_review_fingerprint','x','identity_mismatch'); bad('preparation_review_closure_id','x','identity_mismatch'); bad('preparation_review_closure_fingerprint','x','identity_mismatch'); bad('preparation_id','x','identity_mismatch'); bad('preparation_fingerprint','x','identity_mismatch'); bad('preparation_closure_id','x','identity_mismatch'); bad('invocation_descriptor_id','x','identity_mismatch'); bad('runtime_adapter_admission_id','x','identity_mismatch')
def test_scope_context_and_adapter_rejections():
 bad('adapter_id','*','adapter_identity_mismatch'); bad('adapter_version','*','adapter_version_mismatch'); bad('requested_activation_scope',{'operations':['observe','write']},'scope_expansion'); bad('requested_activation_scope','global','wildcard_scope'); bad('request_context',{'command':'run'},'executable_payload'); bad('activation_constraints',{},'invalid_activation_constraints')
def test_resource_timeout_environment_authority_payloads():
 bad('resource_constraints',{},'unbounded_resources'); bad('resource_constraints',{'x':0},'unbounded_resources'); bad('resource_constraints',{'x':-1},'unbounded_resources'); bad('resource_constraints',{'x':'1'},'unbounded_resources'); bad('timeout_constraints',{},'invalid_timeout'); bad('timeout_constraints',{'seconds':0,'finite':True,'perpetual':False},'invalid_timeout'); bad('timeout_constraints',{'seconds':-1,'finite':True,'perpetual':False},'invalid_timeout'); bad('timeout_constraints',{'seconds':float('inf'),'finite':True,'perpetual':False},'invalid_timeout'); bad('timeout_constraints',{'seconds':1,'finite':True,'perpetual':True},'invalid_timeout'); bad('environment_constraints',{},'invalid_environment_constraints')
 for k,v in [('non_transferable',False),('non_reusable',False),('scope_bound',False),('perpetual',True),('passive',False),('consumed',True),('closed',True),('unrestricted',True)]:
  r=request(); r['authority_constraints'][k]=v; res=val(r); assert not res.valid
 for key in ['command','shell','script','source_code','executable','binary','module_path','callable','entrypoint','patch','diff','activation_callback','activation_command','api_key','private_key','bearer','environment_secrets']:
  r=request(); r['request_context']={key:'x'}; assert not val(r).valid
