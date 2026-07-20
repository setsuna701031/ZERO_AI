from core.engineering.engineering_runtime_execution_coordination import *
def test_execution_disabled_by_default(): assert coordinate_engineering_runtime_execution({}, {}, {}, {}, None)["status"]=="rejected"
def test_duplicate_is_suppressed(): assert coordinate_engineering_runtime_execution({}, {}, {}, {}, None,completed_execution={"status":"succeeded"})["status"]=="duplicate_suppressed"
