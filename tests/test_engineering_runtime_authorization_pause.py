from core.engineering.engineering_runtime_authorization_pause import *
def test_authorizer_is_not_inferred(): assert build_engineering_runtime_authorization_pause({})["status"]=="awaiting_input"
