from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_evidence_excludes_content_paths_and_diffs():
 text=canonical_json(orchestrate_engineering_runtime(request_payload())["evidence"]); assert "proposed_content" not in text and "raw_diff" not in text and ":\\" not in text
