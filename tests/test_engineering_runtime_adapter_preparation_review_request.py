from core.engineering.engineering_runtime_adapter_preparation_review_request import *
from tests.runtime_adapter_preparation_review_fixtures import review_request
def test_valid_review_request_and_determinism():
 r,*_=review_request(); r2,*_=review_request(); assert r==r2; assert validate_runtime_adapter_preparation_review_request(r).valid
def test_request_invalid_cases():
 cases=[({'preparation_status':'not_prepared'}, {}, 'preparation_not_prepared'), ({}, {'package_status':'not_closed'}, 'closure_not_closed'), ({'adapter_id':'bad id'}, {}, 'adapter_identity_mismatch'), ({'adapter_version':'bad version'}, {}, 'adapter_version_mismatch'), ({'prepared_scope':{'files':['*']}}, {}, 'wildcard_scope')]
 for po,co,code in cases:
  r,*_=review_request(preparation_overrides=po,closure_overrides=co); assert code in validate_runtime_adapter_preparation_review_request(r).errors
 for key in ('command','shell','script','source_code','module_path','callable','patch','api_key','private_key','bearer','environment_secrets'):
  r,*_=review_request(review_context={key:'x'}); assert not validate_runtime_adapter_preparation_review_request(r).valid
