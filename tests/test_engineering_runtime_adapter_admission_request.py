from core.engineering.engineering_runtime_adapter_admission_request import *
from tests.runtime_adapter_admission_fixtures import request,AUTH
def test_valid_request_deterministic():
 r,_,_,_=request(); assert r==request()[0]; assert validate_runtime_adapter_admission_request(r).valid; assert inspect_runtime_adapter_admission_request(r)['valid']
def test_malformed_and_bad_values():
 assert not validate_runtime_adapter_admission_request({}).valid
 for kw in ({'adapter':''},{'version':''},{'scope':{'files':['*']}},{'auth':{**AUTH,'unrestricted':True}},{'auth':{**AUTH,'non_transferable':False}},{'auth':{**AUTH,'non_reusable':False}},{'auth':{**AUTH,'perpetual':True}},{'auth':{**AUTH,'command':'run'}},{'auth':{**AUTH,'token':'secret'}}): assert not validate_runtime_adapter_admission_request(request(**kw)[0]).valid
