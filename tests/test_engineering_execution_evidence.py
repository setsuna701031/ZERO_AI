from core.engineering.engineering_execution_evidence import build_engineering_execution_evidence
def test_evidence_requires_records():
 assert build_engineering_execution_evidence({}, {}, {})["integrity_status"]=="insufficient"
