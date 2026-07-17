from hashlib import sha256
from pathlib import Path

import pytest

from core.runtime.runtime_candidate_authoring_engine import author_candidate, create_authoring_request

NOW = "2026-07-12T00:00:00+00:00"


def make_request(tmp_path, strategy, instruction=None, content="x = 1\n", path="app.py"):
    workspace = tmp_path / "workspace"; workspace.mkdir(parents=True)
    target = workspace / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8")
    raw = target.read_bytes(); evidence = [{"relative_path": path, "reference": f"workspace:{path}", "sha256": sha256(raw).hexdigest(), "preview": content}]
    goal = {"goal_id": "g", "mission_id": "m", "goal_type": "modify", "target_scope": [path], "acceptance_criteria": ["exact instruction"], "validation_requirements": ["parse"]}
    body = {"authoring_strategy": strategy, **(instruction or {})}
    request = create_authoring_request(goal=goal, session={"session_id": "s"}, authoring_instruction=body, repository_context_references=evidence, inspect_evidence_references=evidence, now=NOW)
    return workspace, target, request


def test_append_and_engine_does_not_mutate_workspace(tmp_path):
    workspace, target, request = make_request(tmp_path, "append_text", {"append_text": "# authored\n"})
    before = target.read_bytes(); output = author_candidate(request, workspace_root=workspace, now=NOW)
    assert output["status"] == "candidate_ready" and output["candidate_operations"][0]["content"].endswith("# authored\n")
    assert target.read_bytes() == before and output["workspace_mutated"] is False and output["transaction_invoked"] is False


@pytest.mark.parametrize(("old", "reason"), [("missing", "exact_text_zero_matches"), ("x", "exact_text_multiple_matches")])
def test_replace_exact_fail_closed(tmp_path, old, reason):
    workspace, _, request = make_request(tmp_path, "replace_exact_text", {"exact_text": old, "replacement_text": "y"}, content="x x")
    output = author_candidate(request, workspace_root=workspace, now=NOW)
    assert output["status"] == "clarification_required" and reason in output["warnings"] and not output["candidate_operations"]


def test_replace_exact_success_stale_and_unsupported(tmp_path):
    workspace, target, request = make_request(tmp_path, "replace_exact_text", {"exact_text": "x = 1", "replacement_text": "x = 2"})
    assert author_candidate(request, workspace_root=workspace, now=NOW)["candidate_operations"][0]["content"].splitlines() == ["x = 2"]
    target.write_text("changed", encoding="utf-8"); assert "stale_original_fingerprint" in author_candidate(request, workspace_root=workspace, now=NOW)["warnings"]
    workspace2, _, bad = make_request(tmp_path / "other", "freeform", {})
    assert author_candidate(bad, workspace_root=workspace2, now=NOW)["status"] in {"unsupported", "clarification_required"}


def test_create_template_and_python_import(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    goal = {"goal_id": "g", "mission_id": "m", "goal_type": "document", "target_scope": ["new.txt"], "acceptance_criteria": ["create"], "validation_requirements": ["text"]}
    request = create_authoring_request(goal=goal, session={"session_id": "s"}, authoring_instruction={"authoring_strategy": "create_text_file", "content": "hello"}, repository_context_references=[], inspect_evidence_references=[], now=NOW)
    assert author_candidate(request, workspace_root=workspace, now=NOW)["candidate_operations"][0]["operation"] == "create"
    (workspace / "new.txt").write_text("exists"); assert "create_would_overwrite_existing_file" in author_candidate(request, workspace_root=workspace, now=NOW)["warnings"]
    workspace2, _, templ = make_request(tmp_path / "templ", "document_template", {"template": "purpose", "fields": {"purpose": "Why"}}, path="README.md")
    assert "## Purpose" in author_candidate(templ, workspace_root=workspace2, now=NOW)["candidate_operations"][0]["content"]
    workspace3, _, imp = make_request(tmp_path / "imp", "python_import_safe_edit", {"import_statement": "from pathlib import Path"})
    assert author_candidate(imp, workspace_root=workspace3, now=NOW)["status"] == "candidate_ready"


def test_scope_excluded_and_incomplete_instruction(tmp_path):
    workspace, _, request = make_request(tmp_path, "append_text", {})
    assert author_candidate(request, workspace_root=workspace, now=NOW)["status"] == "clarification_required"
    request["excluded_scope"] = ["app.py"]
    from core.runtime.runtime_operator_session import fingerprint
    request["fingerprint"] = fingerprint({k: v for k, v in request.items() if k != "fingerprint"})
    assert "excluded_scope_violation" in author_candidate(request, workspace_root=workspace, now=NOW)["warnings"]
