from __future__ import annotations

from cli.zero_runtime_session import build_parser, run

def test_create_status_and_no_unsafe_flags(tmp_path):
    target = tmp_path / "target"; target.mkdir(); workspace = tmp_path / "workspace"; workspace.mkdir(); session = tmp_path / "session.json"
    result, code = run(["create", "repair", "--target-root", str(target), "--workspace-root", str(workspace), "--session-path", str(session), "--now", "2026-07-12T00:00:00+00:00"])
    assert code == 0 and result["required_action"] == "operator_approval" and session.exists()
    status, code = run(["status", str(session)]); assert code == 0 and status["session_id"] == result["session_id"]
    help_text = build_parser().format_help()
    assert "auto-approve" not in help_text and "skip-validation" not in help_text and "shell" not in help_text
