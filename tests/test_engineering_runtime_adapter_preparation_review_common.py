from core.engineering.engineering_runtime_adapter_preparation_review_common import *
def test_determinism_and_prohibited_payloads():
 a={'b':2,'a':1}; assert canonical_json(a)==canonical_json({'a':1,'b':2}); assert canonical_fingerprint(a)==canonical_fingerprint({'a':1,'b':2}); assert canonical_identity('p-',a)==canonical_identity('p-',{'a':1,'b':2})
 for key in ('command','shell','script','source_code','executable','module_path','import_path','callable','callback','patch','diff','api_key','private_key','bearer','environment_secrets'):
  val=False if key=='executable' else 'x'; assert contains_prohibited({key:val}) is (key!='executable')
 assert contains_prohibited({'x':'Bearer token'}); assert contains_prohibited({'x':'-----BEGIN PRIVATE KEY-----'}); assert contains_wildcard({'files':['*']})
def test_authority_constraints():
 scope={'files':['a']}; good={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'restricted':True,'scope':scope}
 assert authority_valid(good,scope)
 for k,bad in [('non_transferable',False),('non_reusable',False),('scope_bound',False),('perpetual',True),('passive',False),('consumed',True),('closed',True),('unrestricted',True),('restricted',False)]: assert not authority_valid({**good,k:bad},scope)
