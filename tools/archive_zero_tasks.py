from __future__ import annotations

import argparse
import copy
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


PROTECTED_ACTIVE_STATUSES = {
    "running",
    "waiting",
    "waiting_review",
    "review_required",
    "blocked",
    "paused",
}

DEFAULT_ARCHIVE_STATUSES = {
    "finished",
    "failed",
    "error",
    "cancelled",
    "canceled",
    "done",
    "success",
    "completed",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp_path.replace(path)


def _task_id_from_payload(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    return str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()


def _status_from_payload(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or "").strip().lower()


def _split_csv(value: str) -> Set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _iter_task_records(tasks_json: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(tasks_json, list):
        for item in tasks_json:
            if isinstance(item, dict):
                task_id = _task_id_from_payload(item)
                if task_id:
                    yield task_id, item
        return

    if isinstance(tasks_json, dict):
        tasks = tasks_json.get("tasks")

        if isinstance(tasks, list):
            for item in tasks:
                if isinstance(item, dict):
                    task_id = _task_id_from_payload(item)
                    if task_id:
                        yield task_id, item
            return

        if isinstance(tasks, dict):
            for key, item in tasks.items():
                if isinstance(item, dict):
                    task_id = _task_id_from_payload(item) or str(key)
                    if task_id:
                        yield task_id, item
            return

        for key, item in tasks_json.items():
            if isinstance(item, dict):
                task_id = _task_id_from_payload(item) or str(key)
                if task_id:
                    yield task_id, item


def _filter_tasks_json(tasks_json: Any, archive_ids: Set[str]) -> Any:
    if isinstance(tasks_json, list):
        return [
            item for item in tasks_json
            if not (isinstance(item, dict) and _task_id_from_payload(item) in archive_ids)
        ]

    if isinstance(tasks_json, dict):
        filtered = copy.deepcopy(tasks_json)
        tasks = filtered.get("tasks")

        if isinstance(tasks, list):
            filtered["tasks"] = [
                item for item in tasks
                if not (isinstance(item, dict) and _task_id_from_payload(item) in archive_ids)
            ]
            return filtered

        if isinstance(tasks, dict):
            filtered["tasks"] = {
                key: item
                for key, item in tasks.items()
                if str(key) not in archive_ids
                and not (isinstance(item, dict) and _task_id_from_payload(item) in archive_ids)
            }
            return filtered

        for key in list(filtered.keys()):
            item = filtered.get(key)
            if str(key) in archive_ids:
                filtered.pop(key, None)
                continue
            if isinstance(item, dict) and _task_id_from_payload(item) in archive_ids:
                filtered.pop(key, None)

        return filtered

    return tasks_json


def _is_older_than(path: Path, older_than_days: int) -> bool:
    if older_than_days <= 0:
        return True
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds >= older_than_days * 86400


def _archive_then_remove_folder(src: Path, dst: Path) -> Tuple[bool, str]:
    if not src.exists():
        return True, "source_missing"

    if not src.is_dir():
        return False, "source_not_directory"

    dst.parent.mkdir(parents=True, exist_ok=True)
    final_dst = dst
    if final_dst.exists():
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_dst = dst.with_name(f"{dst.name}_{suffix}")

    try:
        shutil.copytree(src, final_dst)
    except Exception as exc:
        return False, f"copy_failed:{type(exc).__name__}:{exc}"

    try:
        shutil.rmtree(src)
    except Exception as exc:
        return False, f"remove_failed:{type(exc).__name__}:{exc}"

    if src.exists():
        return False, "remove_failed:source_still_exists"

    return True, "archived_and_removed"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive completed or selected stale ZERO task records and task folders safely."
    )
    parser.add_argument(
        "--workspace",
        default="workspace",
        help="Workspace directory. Default: workspace",
    )
    parser.add_argument(
        "--status",
        default="finished,failed,error,cancelled,canceled,done,success,completed",
        help="Comma-separated statuses to archive. Example: queued,replanning",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=0,
        help="Only archive task folders older than N days by folder mtime. Default: 0",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="Comma-separated task IDs to preserve even if status matches.",
    )
    parser.add_argument(
        "--include",
        default="",
        help="Comma-separated task IDs to archive even if status does not match.",
    )
    parser.add_argument(
        "--include-missing-folders",
        action="store_true",
        help="Also remove matching tasks.json records when task folder is missing.",
    )
    parser.add_argument(
        "--allow-active",
        action="store_true",
        help="Allow archiving protected active statuses such as waiting_review/review_required/running.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually archive and rewrite tasks.json. Without this, dry-run only.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    tasks_dir = workspace / "tasks"
    tasks_json_path = workspace / "tasks.json"

    archive_statuses = {item.lower() for item in _split_csv(args.status)} or set(DEFAULT_ARCHIVE_STATUSES)
    exclude_ids = _split_csv(args.exclude)
    include_ids = _split_csv(args.include)

    if not workspace.exists():
        print(f"ERROR: workspace not found: {workspace}")
        return 2
    if not tasks_json_path.exists():
        print(f"ERROR: tasks.json not found: {tasks_json_path}")
        return 2

    tasks_json = _load_json(tasks_json_path)
    records = list(_iter_task_records(tasks_json))

    selected: List[Tuple[str, str, Path, bool, str]] = []
    skipped_protected_active = 0
    skipped_excluded = 0
    skipped_young = 0
    skipped_missing = 0
    skipped_status = 0

    for task_id, task in records:
        status = _status_from_payload(task)
        task_dir = tasks_dir / task_id
        exists = task_dir.exists()

        if task_id in exclude_ids:
            skipped_excluded += 1
            continue

        forced_include = task_id in include_ids
        status_matches = status in archive_statuses

        if not forced_include and not status_matches:
            skipped_status += 1
            continue

        if not args.allow_active and status in PROTECTED_ACTIVE_STATUSES:
            skipped_protected_active += 1
            continue

        if exists:
            if not _is_older_than(task_dir, args.older_than_days):
                skipped_young += 1
                continue
        elif not args.include_missing_folders:
            skipped_missing += 1
            continue

        reason = "forced_include" if forced_include and not status_matches else "status_match"
        selected.append((task_id, status, task_dir, exists, reason))

    print("ZERO task cleanup")
    print(f"workspace: {workspace}")
    print(f"tasks.json records: {len(records)}")
    print(f"selected for archive: {len(selected)}")
    print(f"archive statuses: {','.join(sorted(archive_statuses))}")
    print(f"excluded task IDs: {len(exclude_ids)}")
    print(f"forced include task IDs: {len(include_ids)}")
    print(f"skipped protected active/waiting: {skipped_protected_active}")
    print(f"skipped excluded: {skipped_excluded}")
    print(f"skipped status mismatch: {skipped_status}")
    print(f"skipped too new: {skipped_young}")
    print(f"skipped missing folder: {skipped_missing}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")

    for task_id, status, _task_dir, exists, reason in selected[:80]:
        marker = "folder" if exists else "record-only"
        print(f"  {task_id}  {status or '-'}  {marker}  {reason}")
    if len(selected) > 80:
        print(f"  ... {len(selected) - 80} more")

    if not args.apply:
        print("")
        print("Dry-run only. Re-run with --apply to archive.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = workspace / "task_archive" / f"cleanup_{timestamp}"
    archive_tasks_dir = archive_root / "tasks"
    archive_root.mkdir(parents=True, exist_ok=True)

    backup_tasks_json = archive_root / "tasks_before_cleanup.json"
    shutil.copy2(tasks_json_path, backup_tasks_json)

    archive_ids = {task_id for task_id, _status, _task_dir, _exists, _reason in selected}
    filtered_tasks_json = _filter_tasks_json(tasks_json, archive_ids)

    folder_results: List[Dict[str, Any]] = []
    failed_folder_ops: List[Dict[str, Any]] = []

    for task_id, status, task_dir, exists, reason in selected:
        if exists:
            ok, message = _archive_then_remove_folder(task_dir, archive_tasks_dir / task_id)
        else:
            ok, message = True, "record_only_missing_folder"

        item = {
            "task_id": task_id,
            "status": status,
            "source": str(task_dir),
            "exists_before": exists,
            "ok": ok,
            "message": message,
            "reason": reason,
        }
        folder_results.append(item)
        if not ok:
            failed_folder_ops.append(item)

    if failed_folder_ops:
        _write_json(archive_root / "failed_folder_ops.json", failed_folder_ops)
        print("")
        print("ERROR: some folders could not be archived/removed.")
        print(f"Failed folder ops: {archive_root / 'failed_folder_ops.json'}")
        return 3

    _write_json(tasks_json_path, filtered_tasks_json)

    # Final verification: archived IDs should not remain under workspace/tasks.
    remaining = [
        task_id for task_id in sorted(archive_ids)
        if (tasks_dir / task_id).exists()
    ]

    manifest = {
        "created_at": timestamp,
        "workspace": str(workspace),
        "archive_statuses": sorted(archive_statuses),
        "exclude_ids": sorted(exclude_ids),
        "include_ids": sorted(include_ids),
        "older_than_days": args.older_than_days,
        "allow_active": bool(args.allow_active),
        "archived_count": len(selected),
        "archived_task_ids": sorted(archive_ids),
        "folder_results": folder_results,
        "remaining_source_folders_after_cleanup": remaining,
        "backup_tasks_json": str(backup_tasks_json),
    }
    _write_json(archive_root / "manifest.json", manifest)

    print("")
    print(f"Archived {len(selected)} task records.")
    print(f"Archive root: {archive_root}")
    print(f"Backup tasks.json: {backup_tasks_json}")
    if remaining:
        print("WARNING: some source folders still remain:")
        for task_id in remaining[:30]:
            print(f"  {task_id}")
        if len(remaining) > 30:
            print(f"  ... {len(remaining) - 30} more")
        return 4

    print("Verified: archived source folders removed from workspace\\tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
