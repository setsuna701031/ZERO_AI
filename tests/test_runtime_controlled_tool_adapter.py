from __future__ import annotations
import pytest
from core.runtime.runtime_controlled_tool_adapter import *
NOW="2026-07-12T00:00:00+00:00"
def request(tool,path,**kw):return create_tool_request(tool,path,request_id=f"r-{tool}",source_goal_id="g",source_session_id="s",execution_request_fingerprint="e",now=NOW,**kw)
def roots(tmp_path):w=tmp_path/"workspace";a=tmp_path/"artifacts";w.mkdir();return w,a
def test_inspect_utf8_bom_binary_limit_and_paths(tmp_path):
 w,a=roots(tmp_path);(w/"a.txt").write_text("\ufeffhello",encoding="utf-8")
 result=execute_controlled_tool(request("inspect_file","a.txt"),workspace_root=w,artifact_root=a,approved_scope=["a.txt"],now=NOW);assert result["status"]=="completed" and result["result"]["preview"]=="hello"
 for path in ("C:/x.txt","../x.txt","/x.txt"):
  assert execute_controlled_tool(request("inspect_file",path),workspace_root=w,artifact_root=a,approved_scope=["a.txt"],now=NOW)["status"]=="blocked"
 (w/"b.bin").write_bytes(b"a\0b");assert "binary_file_forbidden" in execute_controlled_tool(request("inspect_file","b.bin"),workspace_root=w,artifact_root=a,approved_scope=["b.bin"],now=NOW)["reasons"]
 (w/"big.txt").write_bytes(b"x"*(MAX_FILE_BYTES+1));assert "file_bytes_limit_exceeded" in execute_controlled_tool(request("inspect_file","big.txt"),workspace_root=w,artifact_root=a,approved_scope=["big.txt"],now=NOW)["reasons"]
def test_candidate_is_artifact_only_and_preserves_original(tmp_path):
 w,a=roots(tmp_path);path=w/"a.txt";path.write_text("before",encoding="utf-8");before=path.read_bytes()
 result=execute_controlled_tool(request("write_text_candidate","a.txt",content="after",operation="replace"),workspace_root=w,artifact_root=a,approved_scope=["a.txt"],now=NOW)
 assert result["status"]=="completed" and path.read_bytes()==before and result["workspace_mutated"] is False
 item=result["result"];assert item["expected_original_sha256"] and item["candidate_reference"] and item["tool_adapter_contract"]==CONTRACT
def test_compile_text_validation_and_unsupported(tmp_path):
 w,a=roots(tmp_path);(w/"a.py").write_text("x=1\n",encoding="utf-8");good=execute_controlled_tool(request("validate_python_source","a.py",content="x=2\n"),workspace_root=w,artifact_root=a,approved_scope=["a.py"],now=NOW);bad=execute_controlled_tool(request("validate_python_source","a.py",content="def bad(:"),workspace_root=w,artifact_root=a,approved_scope=["a.py"],now=NOW)
 assert good["result"]["passed"] is True and bad["result"]["passed"] is False and not good["result"]["executed"]
 assert execute_controlled_tool(request("unknown","a.py"),workspace_root=w,artifact_root=a,approved_scope=["a.py"],now=NOW)["status"]=="blocked"
def test_symlink_rejected_or_unavailable(tmp_path):
 w,a=roots(tmp_path);outside=tmp_path/"outside.txt";outside.write_text("x");link=w/"link.txt"
 try:link.symlink_to(outside)
 except OSError:pytest.skip("symlink unavailable")
 assert execute_controlled_tool(request("inspect_file","link.txt"),workspace_root=w,artifact_root=a,approved_scope=["link.txt"],now=NOW)["status"]=="blocked"
