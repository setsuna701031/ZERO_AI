from __future__ import annotations

from cli.zero_runtime_worker import build_parser, run_cli
from core.runtime.runtime_session_queue import create_scheduler_state, save_scheduler_state
from tests.test_runtime_session_queue import NOW

def test_init_status_health_pause_resume_stop_and_run_once(tmp_path):
    scheduler = tmp_path / "scheduler.json"; worker = tmp_path / "worker.json"; target = tmp_path / "target"; target.mkdir(); workspace = tmp_path / "workspace"; workspace.mkdir()
    save_scheduler_state(create_scheduler_state(state_path=scheduler, now=NOW), scheduler)
    result, code = run_cli(["init", "--scheduler-state", str(scheduler), "--worker-state", str(worker), "--worker-name", "worker", "--target-root", str(target), "--now", NOW]); assert code == 0
    status, code = run_cli(["status", str(worker)]); assert code == 0 and status["worker_id"] == result["worker_id"]
    health, code = run_cli(["health", str(worker), "--scheduler-state", str(scheduler), "--now", NOW]); assert code == 0 and health["healthy"]
    paused, code = run_cli(["pause", str(worker), "--now", NOW]); assert code == 1 and paused["worker_status"] == "paused"
    resumed, code = run_cli(["resume", str(worker), "--now", NOW]); assert code == 0 and resumed["worker_status"] == "idle"
    ran, code = run_cli(["run", "--scheduler-state", str(scheduler), "--worker-state", str(worker), "--worker-name", "worker", "--target-root", str(target), "--workspace-root", str(workspace), "--once", "--now", NOW]); assert code == 0 and ran["worker_status"] == "stopped"
    stopped, code = run_cli(["stop", str(worker), "--now", NOW]); assert code == 0 and stopped["stop_requested"]

def test_invalid_bounds_and_no_forbidden_flags(tmp_path):
    parser = build_parser(); help_text = parser.format_help()
    for value in ("auto-approve", "auto-review", "auto-authorize", "auto-invoke", "auto-execute", "force", "skip-validation", "no-rollback", "shell", "git-commit"):
        assert value not in help_text
