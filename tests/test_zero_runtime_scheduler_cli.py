from __future__ import annotations

from cli.zero_runtime_scheduler import build_parser, run
from tests.test_runtime_session_queue import NOW, session_file

def test_init_enqueue_list_waiting_stats_restart(tmp_path):
    state = tmp_path / "state.json"; result, code = run(["init", "--state-path", str(state), "--now", NOW]); assert code == 0
    path, session, target, workspace = session_file(tmp_path, "cli")
    result, code = run(["enqueue", str(state), str(path), "--priority", "high", "--target-root", str(target), "--workspace-root", str(workspace), "--now", NOW]); assert code == 0
    listed, code = run(["list", str(state)]); assert code == 0 and listed["entries"][0]["priority"] == 10
    waiting, _ = run(["waiting", str(state)]); assert waiting["waiting_operator_sessions"][0]["session_id"] == session["session_id"]
    stats, _ = run(["stats", str(state)]); assert stats["waiting_operator"] == 1
    lease, code = run(["lease-next", str(state), "--owner", "worker", "--now", NOW]); assert code == 1 and lease["lease"] is None

def test_no_forbidden_flags():
    help_text = build_parser().format_help()
    for value in ("auto-approve", "auto-review", "auto-authorize", "auto-invoke", "auto-execute", "force", "skip-validation", "no-rollback", "shell", "git-commit"):
        assert value not in help_text
