from core.engineering.engineering_runtime_transaction_coordination import *
def test_transaction_requires_authorization(): assert coordinate_engineering_runtime_transaction({"status":"awaiting_input"})["status"]=="blocked"
