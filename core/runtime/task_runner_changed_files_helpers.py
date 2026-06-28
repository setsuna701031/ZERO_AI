from __future__ import annotations

from typing import Any, List


def extract_changed_files_from_step_result(step_result: Any) -> List[str]:
    files: List[str] = []

    def _collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            item = value.strip()
            if item not in files:
                files.append(item)
            return
        if isinstance(value, list):
            for child in value:
                _collect(child)
            return
        if isinstance(value, dict):
            for key in ("changed_files", "modified_files", "created_files", "written_files", "files"):
                if key in value:
                    _collect(value.get(key))

    _collect(step_result)
    if isinstance(step_result, dict):
        for key in ("result", "rollback_result"):
            payload = step_result.get(key)
            if isinstance(payload, dict):
                _collect(payload)
    return files
