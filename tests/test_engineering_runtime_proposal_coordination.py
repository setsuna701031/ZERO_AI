from core.engineering.engineering_runtime_proposal_coordination import *
def test_proposal_requires_explicit_artifact(): assert coordinate_engineering_runtime_proposal({"status":"coordinated"})["status"]=="blocked"
