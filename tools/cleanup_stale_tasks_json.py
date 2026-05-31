from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


PROTECTED_STATUSES = {
    "running",
    "waiting",
    "waiting_review",
    "review_required",
    "blocked",
    "paused",
}


def _split_csv(value: str) -> Set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def _task_id(task: Any, fallback: str = "") -> str:
    if not isinstance(task, dict):
        return fallback
    return str(task.get("task_id") or task.get("task_name") or task.get("id") or fallback or "").strip()


def _task_status(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or "").strip().lower()


def _iter_records(tasks_json: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(tasks_json, list):
        for item in tasks_json:
            if isinstance(item, dict):
                tid = _task_id(item)
                if tid:
                    yield tid, item
        return

    if isinstance(tasks_json, dict):
        tasks = tasks_json.get("tasks")

        if isinstance(tasks, list):
            for item in tasks:
                if isinstance(item, dict):
                    tid = _task_id(item)
                    if tid:
                        yield tid, item
            return

        if isinstance(tasks, dict):
            for key, item in tasks.items():
                if isinstance(item, dict):
                    tid = _task_id(item, fallback=str(key))
                    if tid:
                        yield tid, item
            return

        for key, item in tasks_json.items():
            if isinstance(item, dict):
                tid = _task_id(item, fallback=str(key))
                if tid:
                    yield tid, item


def _remove_ids_from_tasks_json(tasks_json: Any, remove_ids: Set[str]) -> Any:
    if isinstance(tasks_json, list):
        return [
            item for item in tasks_json
            if not (isinstance(item, dict) and _task_id(item) in remove_ids)
        ]

    if isinstance(tasks_json, dict):
        result = copy.deepcopy(tasks_json)
        tasks = result.get("tasks")

        if isinstance(tasks, list):
            result["tasks"] = [
                item for item in tasks
                if not (isinstance(item, dict) and _task_id(item) in remove_ids)
            ]
            return result

        if isinstance(tasks, dict):
            result["tasks"] = {
                key: value
                for key, value in tasks.items()
                if str(key) not in remove_ids
                and not (isinstance(value, dict) and _task_id(value, fallback=str(key)) in remove_ids)
            }
            return result

        for key in list(result.keys()):
            value = result.get(key)
            if str(key) in remove_ids:
                result.pop(key, None)
                continue
            if isinstance(value, dict) and _task_id(value, fallback=str(key)) in remove_ids:
                result.pop(key, None)

        return result

    return tasks_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove stale ZERO task records from workspace/tasks.json when their task folders are already gone."
    )
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument(
        "--status",
        default="queued,replanning",
        help="Comma-separated statuses eligible for removal. Default: queued,replanning",
    )
    parser.add_argument(
        "--exclude",
        default="review-approve-1,task_1780034851444,task_1780037719677,task_1780037735945",
        help="Comma-separated task IDs to keep.",
    )
    parser.add_argument(
        "--allow-protected",
        action="store_true",
        help="Allow removal of protected statuses such as waiting_review/running.",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    tasks_dir = workspace / "tasks"
    tasks_json_path = workspace / "tasks.json"
    archive_dir = workspace / "task_archive"

    if not tasks_json_path.exists():
        print(f"ERROR: missing tasks.json: {tasks_json_path}")
        return 2

    statuses = {s.lower() for s in _split_csv(args.status)}
    exclude_ids = _split_csv(args.exclude)

    tasks_json = _load_json(tasks_json_path)
    records = list(_iter_records(tasks_json))

    remove_ids: Set[str] = set()
    keep_count = 0
    skipped_protected = 0
    skipped_status = 0
    skipped_excluded = 0

    for tid, task in records:
        status = _task_status(task)

        if tid in exclude_ids:
            skipped_excluded += 1
            continue

        if status in PROTECTED_STATUSES and not args.allow_protected:
            skipped_protected += 1
            continue

        if status not in statuses:
            skipped_status += 1
            continue

        task_folder = tasks_dir / tid
        if task_folder.exists():
            keep_count += 1
            continue

        remove_ids.add(tid)

    print("ZERO tasks.json stale record cleanup")
    print(f"workspace: {workspace}")
    print(f"records: {len(records)}")
    print(f"eligible statuses: {','.join(sorted(statuses))}")
    print(f"excluded ids: {len(exclude_ids)}")
    print(f"selected stale records: {len(remove_ids)}")
    print(f"kept because folder exists: {keep_count}")
    print(f"skipped protected: {skipped_protected}")
    print(f"skipped status mismatch: {skipped_status}")
    print(f"skipped excluded: {skipped_excluded}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")

    for tid in sorted(remove_ids)[:100]:
        print(f"  {tid}")
    if len(remove_ids) > 100:
        print(f"  ... {len(remove_ids) - 100} more")

    if not args.apply:
        print("")
        print("Dry-run only. Re-run with --apply to write tasks.json.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cleanup_dir = archive_dir / f"tasks_json_stale_cleanup_{timestamp}"
    cleanup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = cleanup_dir / "tasks_before_stale_cleanup.json"
    shutil.copy2(tasks_json_path, backup_path)

    filtered = _remove_ids_from_tasks_json(tasks_json, remove_ids)
    _write_json(tasks_json_path, filtered)

    manifest = {
        "created_at": timestamp,
        "workspace": str(workspace),
        "removed_count": len(remove_ids),
        "removed_task_ids": sorted(remove_ids),
        "backup_tasks_json": str(backup_path),
        "statuses": sorted(statuses),
        "exclude_ids": sorted(exclude_ids),
    }
    _write_json(cleanup_dir / "manifest.json", manifest)

    print("")
    print(f"Removed {len(remove_ids)} stale records from tasks.json.")
    print(f"Backup: {backup_path}")
    print(f"Manifest: {cleanup_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
