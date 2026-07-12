from pathlib import Path
from core.runtime.runtime_goal_executor import create_goal_execution_request,execute_goal
from core.runtime.runtime_operator_session import seal_session

NOW="2026-07-12T00:00:00+00:00"
def test_executor_uses_authoring_engine_and_workspace_stays_unchanged(tmp_path):
 workspace=tmp_path/"workspace";artifacts=tmp_path/"artifacts";workspace.mkdir();target=workspace/"app.py";target.write_text("x=1\n")
 goal={"goal_id":"g","mission_id":"m","goal_type":"modify","target_scope":["app.py"],"goal_fingerprint":"gf","acceptance_criteria":["append exact comment"],"validation_requirements":["python parse"]}
 session=seal_session({"contract":"zero.runtime.operator_session.v1","session_id":"s","session_status":"created","artifacts":{},"artifact_fingerprints":{}})
 request=create_goal_execution_request(goal,session,operator_context={"authoring_strategy":"append_text","append_text":"# ZERO authored candidate\n"},now=NOW)
 before=target.read_bytes();result=execute_goal(request,workspace_root=workspace,artifact_root=artifacts,now=NOW)
 assert result["execution_status"]=="candidate_ready" and result["authoring_output"]["status"]=="candidate_ready"
 assert target.read_bytes()==before and Path(result["candidate_files"][0]["candidate_reference"]).read_text().endswith("# ZERO authored candidate\n")
def test_ambiguous_instruction_clarifies_without_candidate_or_transaction(tmp_path):
 workspace=tmp_path/"workspace";artifacts=tmp_path/"artifacts";workspace.mkdir();target=workspace/"app.py";target.write_text("x=1\n")
 goal={"goal_id":"g","mission_id":"m","goal_type":"modify","target_scope":["app.py"],"goal_fingerprint":"gf","acceptance_criteria":["improve"],"validation_requirements":["python parse"]}
 session=seal_session({"contract":"zero.runtime.operator_session.v1","session_id":"s","session_status":"created","artifacts":{},"artifact_fingerprints":{}})
 result=execute_goal(create_goal_execution_request(goal,session,operator_context={},now=NOW),workspace_root=workspace,artifact_root=artifacts,now=NOW)
 assert result["execution_status"]=="clarification_required" and not result["candidate_files"] and result["transaction_invoked"] is False
