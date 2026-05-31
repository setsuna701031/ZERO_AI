from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


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
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    tmp_path.replace(path)


def _task_id(task: Any, fallback: str = "") -> str:
    if not isinstance(task, dict):
        return fallback
    return str(task.get("task_id") or task.get("task_name") or task.get("id") or fallback or "").strip()


def _task_status(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or "").strip().lower()


def _extract_tasks_container(payload: Any) -> Tuple[str, List[Dict[str, Any]]]:
    if isinstance(payload, list):
        return "list", [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        tasks = payload.get("tasks")

        if isinstance(tasks, list):
            return "dict_tasks_list", [item for item in tasks if isinstance(item, dict)]

        if isinstance(tasks, dict):
            normalized: List[Dict[str, Any]] = []
            for key, value in tasks.items():
                if isinstance(value, dict):
                    item = copy.deepcopy(value)
                    if not _task_id(item):
                        item["task_id"] = str(key)
                    normalized.append(item)
            return "dict_tasks_dict", normalized

        normalized = []
        for key, value in payload.items():
            if isinstance(value, dict):
                item = copy.deepcopy(value)
                if not _task_id(item):
                    item["task_id"] = str(key)
                normalized.append(item)
        if normalized:
            return "dict_root_records", normalized

    return "unknown", []


def _replace_tasks_container(payload: Any, container_kind: str, kept_tasks: List[Dict[str, Any]]) -> Any:
    if container_kind == "list":
        return kept_tasks

    if isinstance(payload, dict):
        result = copy.deepcopy(payload)

        if container_kind == "dict_tasks_list":
            result["tasks"] = kept_tasks
            return result

        if container_kind == "dict_tasks_dict":
            result["tasks"] = {_task_id(item): item for item in kept_tasks if _task_id(item)}
            return result

        if container_kind == "dict_root_records":
            return {_task_id(item): item for item in kept_tasks if _task_id(item)}

    return payload


def _safe_archive_folder(task_dir: Path, archive_tasks_dir: Path, task_id: str) -> str:
    if not task_dir.exists():
        return "folder_missing"

    archive_tasks_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_tasks_dir / task_id
    if destination.exists():
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = archive_tasks_dir / f"{task_id}_{suffix}"

    shutil.copytree(task_dir, destination)
    shutil.rmtree(task_dir)

    if task_dir.exists():
        raise RuntimeError(f"failed to remove source folder: {task_dir}")

    return str(destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hard-clean ZERO tasks.json records and matching task folders."
    )
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument(
        "--status",
        default="queued,replanning",
        help="Comma-separated statuses to remove. Default: queued,replanning",
    )
    parser.add_argument(
        "--exclude",
        default="review-approve-1,task_1780034851444,task_1780037719677,task_1780037735945",
        help="Comma-separated task IDs to preserve.",
    )
    parser.add_argument("--allow-protected", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    tasks_json_path = workspace / "tasks.json"
    tasks_dir = workspace / "tasks"

    if not tasks_json_path.exists():
        print(f"ERROR: missing tasks.json: {tasks_json_path}")
        return 2

    statuses = {item.lower() for item in _split_csv(args.status)}
    exclude_ids = _split_csv(args.exclude)

    payload = _load_json(tasks_json_path)
    container_kind, tasks = _extract_tasks_container(payload)

    remove_tasks: List[Dict[str, Any]] = []
    keep_tasks: List[Dict[str, Any]] = []

    for task in tasks:
        tid = _task_id(task)
        status = _task_status(task)

        if tid in exclude_ids:
            keep_tasks.append(task)
            continue

        if status in PROTECTED_STATUSES and not args.allow_protected:
            keep_tasks.append(task)
            continue

        if status in statuses:
            remove_tasks.append(task)
        else:
            keep_tasks.append(task)

    remove_ids = {_task_id(task) for task in remove_tasks if _task_id(task)}

    print("ZERO hard task index cleanup")
    print(f"workspace: {workspace}")
    print(f"tasks_json: {tasks_json_path}")
    print(f"container_kind: {container_kind}")
    print(f"records_before: {len(tasks)}")
    print(f"selected_remove: {len(remove_tasks)}")
    print(f"records_after: {len(keep_tasks)}")
    print(f"remove_statuses: {','.join(sorted(statuses))}")
    print(f"exclude_ids: {len(exclude_ids)}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")

    for tid in sorted(remove_ids)[:120]:
        print(f"  {tid}")
    if len(remove_ids) > 120:
        print(f"  ... {len(remove_ids) - 120} more")

    if not args.apply:
        print("")
        print("Dry-run only. Re-run with --apply to clean tasks.json and folders.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = workspace.parent / "zero_ai_archives" / f"hard_task_cleanup_{timestamp}"
    archive_tasks_dir = archive_root / "tasks"
    archive_root.mkdir(parents=True, exist_ok=True)

    backup_path = archive_root / "tasks_before_hard_cleanup.json"
    shutil.copy2(tasks_json_path, backup_path)

    folder_archive_results: Dict[str, str] = {}
    for tid in sorted(remove_ids):
        folder_archive_results[tid] = _safe_archive_folder(tasks_dir / tid, archive_tasks_dir, tid)

    new_payload = _replace_tasks_container(payload, container_kind, keep_tasks)
    _write_json(tasks_json_path, new_payload)

    verify_payload = _load_json(tasks_json_path)
    _verify_kind, verify_tasks = _extract_tasks_container(verify_payload)
    remaining = sorted(tid for tid in remove_ids if any(_task_id(task) == tid for task in verify_tasks))

    manifest = {
        "created_at": timestamp,
        "workspace": str(workspace),
        "tasks_json": str(tasks_json_path),
        "backup_tasks_json": str(backup_path),
        "container_kind": container_kind,
        "records_before": len(tasks),
        "records_after": len(verify_tasks),
        "removed_count": len(remove_ids),
        "removed_task_ids": sorted(remove_ids),
        "remaining_removed_ids_after_write": remaining,
        "folder_archive_results": folder_archive_results,
    }
    _write_json(archive_root / "manifest.json", manifest)

    print("")
    print(f"Backup: {backup_path}")
    print(f"Manifest: {archive_root / 'manifest.json'}")
    print(f"Removed records: {len(remove_ids)}")
    print(f"Verified records after write: {len(verify_tasks)}")

    if remaining:
        print("ERROR: some removed task IDs still exist in tasks.json:")
        for tid in remaining[:50]:
            print(f"  {tid}")
        return 3

    print("Verified: selected task IDs removed from tasks.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
