from __future__ import annotations
from core.runtime.runtime_goal_executor import *
from core.runtime.runtime_operator_session import seal_session
NOW="2026-07-12T00:00:00+00:00"
def values(tmp_path,kind="modify",scope=None,context=None):
 w=tmp_path/"workspace";a=tmp_path/"artifacts";w.mkdir();(w/"a.py").write_text("x=1\n",encoding="utf-8");g={"goal_id":"g","mission_id":"m","goal_type":kind,"target_scope":scope or["a.py"],"goal_fingerprint":"gf"};s=seal_session({"session_id":"s","session_fingerprint":"old"});r=create_goal_execution_request(g,s,operator_context=context or{"append_text":"# comment\n"},now=NOW);return w,a,r
def test_executor_candidate_validation_and_no_runtime_authority(tmp_path):
 w,a,r=values(tmp_path);before=(w/"a.py").read_bytes();result=execute_goal(r,workspace_root=w,artifact_root=a,now=NOW)
 assert result["execution_status"]=="candidate_ready" and result["candidate_files"] and result["validation_evidence"][0]["passed"]
 assert (w/"a.py").read_bytes()==before
 for key in ("workspace_mutated","session_created","queue_mutated","transaction_invoked","commit_performed"):assert result[key] is False
def test_validation_failure_unsupported_type_scope_and_context(tmp_path):
 w,a,r=values(tmp_path,context={"replacement_text":"def broken(:"});assert execute_goal(r,workspace_root=w,artifact_root=a,now=NOW)["execution_status"]=="validation_failed"
 second=tmp_path/"second";second.mkdir();w,a,r=values(second,kind="composite");assert execute_goal(r,workspace_root=w,artifact_root=a,now=NOW)["execution_status"]=="blocked"
 third=tmp_path/"third";third.mkdir();w,a,r=values(third,scope=[]);r["approved_scope"]=[]
 from core.runtime.runtime_operator_session import fingerprint
 r["execution_request_fingerprint"]=fingerprint({k:v for k,v in r.items() if k!="execution_request_fingerprint"});assert execute_goal(r,workspace_root=w,artifact_root=a,now=NOW)["execution_status"]=="blocked"
