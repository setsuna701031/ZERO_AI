from __future__ import annotations

from pathlib import Path
import core.tasks.work_package_scheduler as work_package_scheduler_module

from core.tasks.work_package_scheduler import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    WorkPackageScheduler,
)


def _write_scope(repo_root: Path) -> None:
    target = repo_root / "core/agent/agent_loop.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def run():\n"
        "    previous_result = None\n"
        "    return previous_result\n",
        encoding="utf-8",
    )


def _payload(package_id: str = "legacy_audit") -> dict[str, object]:
    return {
        "package_id": package_id,
        "kind": "readonly_audit",
        "mode": "explore",
        "title": "Legacy path audit",
        "scope_paths": ["core/agent/agent_loop.py"],
        "report_path": f"workspace/{package_id}.md",
    }


def test_work_package_scheduler_submit_runs_package(tmp_path: Path) -> None:
    _write_scope(tmp_path)
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    result = scheduler.submit(_payload("audit_submit"))

    assert result["status"] == STATUS_COMPLETED
    assert result["result"]["ok"] is True
    assert result["result"]["package_id"] == "audit_submit"
    assert (tmp_path / "workspace/audit_submit.md").exists()


def test_work_package_scheduler_can_queue_without_execution(tmp_path: Path) -> None:
    _write_scope(tmp_path)
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    result = scheduler.submit(_payload("audit_queue"), execute=False)

    assert result["status"] == STATUS_QUEUED
    assert result["result"] is None
    assert not (tmp_path / "workspace/audit_queue.md").exists()

    ran = scheduler.run("audit_queue")
    assert ran["status"] == STATUS_COMPLETED
    assert (tmp_path / "workspace/audit_queue.md").exists()


def test_work_package_scheduler_status_and_list(tmp_path: Path) -> None:
    _write_scope(tmp_path)
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    scheduler.submit(_payload("audit_one"))
    scheduler.submit(_payload("audit_two"), execute=False)

    one = scheduler.status("audit_one")
    two = scheduler.status("audit_two")
    all_records = scheduler.list()

    assert one["status"] == STATUS_COMPLETED
    assert two["status"] == STATUS_QUEUED
    assert [record["package_id"] for record in all_records] == ["audit_one", "audit_two"]


def test_work_package_scheduler_resume_completed_metadata(tmp_path: Path) -> None:
    _write_scope(tmp_path)
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    scheduler.submit(_payload("audit_resume_done"))
    resumed = scheduler.resume("audit_resume_done")

    assert resumed["status"] == STATUS_COMPLETED
    assert resumed["resumed"] is True
    assert resumed["resume_mode"] == "metadata"


def test_work_package_scheduler_resume_queued_runs_package(tmp_path: Path) -> None:
    _write_scope(tmp_path)
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    scheduler.submit(_payload("audit_resume_queue"), execute=False)
    resumed = scheduler.resume("audit_resume_queue")

    assert resumed["status"] == STATUS_COMPLETED
    assert resumed["resumed"] is True
    assert resumed["resume_mode"] == "run_queued"
    assert (tmp_path / "workspace/audit_resume_queue.md").exists()


def test_work_package_scheduler_failed_package_is_recorded(tmp_path: Path) -> None:
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    result = scheduler.submit(
        {
            "package_id": "audit_missing",
            "kind": "readonly_audit",
            "mode": "explore",
            "title": "Missing file audit",
            "scope_paths": ["core/missing.py"],
            "report_path": "workspace/audit_missing.md",
        }
    )

    assert result["status"] == STATUS_FAILED
    assert result["result"]["ok"] is False
    assert result["error"] == "work_package_failed"
    assert (tmp_path / "workspace/audit_missing.md").exists()


def test_work_package_scheduler_does_not_complete_from_ok_mapping_alone(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scheduler = WorkPackageScheduler(repo_root=tmp_path)
    monkeypatch.setattr(
        work_package_scheduler_module,
        "submit_work_package",
        lambda *_args, **_kwargs: {"ok": True, "package_id": "forged-ok"},
    )

    result = scheduler.submit(_payload("forged-ok"))

    assert result["status"] == STATUS_FAILED
