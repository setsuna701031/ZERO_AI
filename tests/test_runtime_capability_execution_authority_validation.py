from tests.test_runtime_capability_execution_authority import authority
from core.runtime.runtime_capability_execution_authority_validation import validate_capability_execution_authority as validate
def test_validation():
    x=authority();assert validate(x).valid;x["authority_constraints"]["mutation_permission"]=True;assert not validate(x).valid
