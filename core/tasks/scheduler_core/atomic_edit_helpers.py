from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AtomicEditRecord:
    path: str
    before: str
    after: str
    backup_path: str = ""
    changed: bool = False


class AtomicEditSession:
    """Small file-edit transaction helper for scheduler code edits.

    The session stages text writes first.  commit() creates backups and writes
    all staged files.  If any write fails, rollback() restores every file that
    already had a backup in this session.
    """

    def __init__(self, backup_suffix: Optional[str] = None) -> None:
        safe_suffix = backup_suffix or f"v5_7_0_{int(time.time())}"
        self.backup_suffix = str(safe_suffix).replace(" ", "_")
        self.records: List[AtomicEditRecord] = []
        self.committed = False
        self.rollback_applied = False

    def add_write(self, path: str, before: str, after: str) -> None:
        abs_path = os.path.abspath(str(path or ""))
        if not abs_path:
            raise ValueError("atomic write missing path")
        before_text = "" if before is None else str(before)
        after_text = "" if after is None else str(after)
        self.records.append(
            AtomicEditRecord(
                path=abs_path,
                before=before_text,
                after=after_text,
                changed=before_text != after_text,
            )
        )

    def has_changes(self) -> bool:
        return any(record.changed for record in self.records)

    def commit(self) -> Dict[str, Any]:
        changed_records = [record for record in self.records if record.changed]
        written: List[str] = []
        backups: List[str] = []

        try:
            for record in changed_records:
                parent = os.path.dirname(record.path)
                if parent:
                    os.makedirs(parent, exist_ok=True)

                backup_path = f"{record.path}.bak_{self.backup_suffix}"
                counter = 1
                candidate = backup_path
                while os.path.exists(candidate):
                    counter += 1
                    candidate = f"{backup_path}_{counter}"

                if os.path.exists(record.path):
                    shutil.copy2(record.path, candidate)
                else:
                    with open(candidate, "w", encoding="utf-8", newline="") as f:
                        f.write("")

                record.backup_path = candidate
                backups.append(candidate)

            for record in changed_records:
                with open(record.path, "w", encoding="utf-8", newline="") as f:
                    f.write(record.after)
                written.append(record.path)

            self.committed = True
            return {
                "ok": True,
                "committed": True,
                "rollback_applied": False,
                "changed_files": written,
                "backup_files": backups,
                "staged_count": len(self.records),
                "changed_count": len(changed_records),
            }
        except Exception as exc:
            rollback = self.rollback()
            return {
                "ok": False,
                "committed": False,
                "rollback_applied": bool(rollback.get("rollback_applied")),
                "changed_files": written,
                "backup_files": backups,
                "failed_file": getattr(record, "path", ""),
                "failed_reason": str(exc),
                "rollback": rollback,
                "staged_count": len(self.records),
                "changed_count": len(changed_records),
            }

    def rollback(self) -> Dict[str, Any]:
        restored: List[str] = []
        errors: List[Dict[str, str]] = []
        for record in reversed(self.records):
            if not record.backup_path:
                continue
            try:
                if os.path.exists(record.backup_path):
                    parent = os.path.dirname(record.path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    shutil.copy2(record.backup_path, record.path)
                    restored.append(record.path)
            except Exception as exc:
                errors.append({"path": record.path, "error": str(exc)})
        self.rollback_applied = bool(restored or errors)
        return {
            "ok": not errors,
            "rollback_applied": self.rollback_applied,
            "restored_files": restored,
            "errors": errors,
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "staged_count": len(self.records),
            "changed_count": sum(1 for record in self.records if record.changed),
            "paths": [record.path for record in self.records],
            "backup_files": [record.backup_path for record in self.records if record.backup_path],
            "committed": self.committed,
            "rollback_applied": self.rollback_applied,
        }
