from core.engineering.engineering_governed_execution_verification import build_engineering_governed_execution_verification
def test_verification_fails_closed():
 assert build_engineering_governed_execution_verification({}, {}, {}, {}, {}, {}, {})["verification_status"]!="verified"
