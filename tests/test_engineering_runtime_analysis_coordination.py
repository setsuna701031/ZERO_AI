from core.engineering.engineering_runtime_analysis_coordination import *
def test_analysis_blocks_without_required_evidence(): assert coordinate_engineering_runtime_analysis({"requested_orchestration_mode":"analyze","request_id":"r"})["status"]=="blocked"
