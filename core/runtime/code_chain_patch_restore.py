from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def request_code_chain_patch_restore(*, target_path: str, backup_path: str) -> Dict[str, Any]:
    """Restore a Code Chain patch target from its pre-patch backup."""
    normalized_target = str(target_path or "").replace("\\", "/").strip()
    normalized_backup = str(backup_path or "").replace("\\", "/").strip()
    result: Dict[str, Any] = {
        "ok": False,
        "target_path": normalized_target,
        "backup_path": normalized_backup,
        "reason": "rollback_not_run",
        "error": None,
    }

    if not normalized_target or not normalized_backup:
        result["reason"] = "rollback_missing_path"
        result["error"] = "target_path or backup_path is empty"
        return result

    try:
        target = Path(normalized_target)
        backup = Path(normalized_backup)
        if not backup.exists() or not backup.is_file():
            result["reason"] = "backup_missing"
            result["error"] = f"backup not found: {normalized_backup}"
            return result
        before_content = backup.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(before_content, encoding="utf-8")
        result["ok"] = True
        result["reason"] = "rollback_restored_from_backup"
        result["error"] = None
        return result
    except Exception as e:
        result["reason"] = "rollback_failed"
        result["error"] = f"rollback failed: {type(e).__name__}: {e}"
        return result
