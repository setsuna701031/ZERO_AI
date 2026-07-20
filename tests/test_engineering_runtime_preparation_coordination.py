from core.engineering.engineering_runtime_preparation_coordination import *
def test_preparation_requires_verified_approval(): assert coordinate_engineering_runtime_preparation({"status":"awaiting_input"})["status"]=="blocked"
