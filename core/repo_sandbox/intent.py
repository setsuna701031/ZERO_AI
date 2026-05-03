"""Natural-language intent parsing for controlled repo edit tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_ALLOWED_PREFIX = "workspace/"


@dataclass(frozen=True)
class CodeEditIntent:
    status: str
    file_path: Optional[str] = None
    mode: Optional[str] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    reason: Optional[str] = None

    def to_payload(self) -> dict:
        if self.status != "ready":
            return {
                "status": self.status,
                "reason": self.reason,
                "file_path": self.file_path,
            }

        return {
            "file_path": self.file_path,
            "instruction": self.reason or "Controlled replace_text edit.",
            "mode": self.mode,
            "old_text": self.old_text,
            "new_text": self.new_text,
        }


def _normalize_path(path: str) -> str:
    cleaned = path.strip().strip("'\"`.,").replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _is_safe_workspace_path(path: str) -> bool:
    normalized = _normalize_path(path)

    if not normalized.startswith(_ALLOWED_PREFIX):
        return False

    lowered = normalized.lower()

    blocked_parts = [
        ".git",
        "__pycache__",
        ".env",
        "venv/",
        ".venv/",
        "site-packages",
        "token",
        "secret",
        "password",
        "credential",
        "key",
    ]

    return not any(part in lowered for part in blocked_parts)


def _extract_file_path(text: str) -> Optional[str]:
    patterns = [
        r"([A-Za-z0-9_\-./\\]+\.py)",
        r"file_path\s*[:=]\s*['\"]?([^'\"\s]+)",
        r"file\s+['\"]?([^'\"\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _normalize_path(match.group(1))

    return None


def _extract_replace_pair(text: str) -> tuple[Optional[str], Optional[str]]:
    patterns = [
        r"replace\s+['\"](.+?)['\"]\s+with\s+['\"](.+?)['\"]",
        r"change\s+['\"](.+?)['\"]\s+to\s+['\"](.+?)['\"]",
        r"old_text\s*[:=]\s*['\"](.+?)['\"].*?new_text\s*[:=]\s*['\"](.+?)['\"]",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1), match.group(2)

    value_match = re.search(
        r"change\s+VALUE\s+from\s+([0-9]+)\s+to\s+([0-9]+)",
        text,
        flags=re.IGNORECASE,
    )
    if value_match:
        return f"VALUE = {value_match.group(1)}", f"VALUE = {value_match.group(2)}"

    return None, None


def parse_code_edit_intent(task_text: str) -> CodeEditIntent:
    if not task_text or not task_text.strip():
        return CodeEditIntent(status="blocked", reason="empty task text")

    file_path = _extract_file_path(task_text)

    if not file_path:
        return CodeEditIntent(status="blocked", reason="no explicit file path found")

    if not _is_safe_workspace_path(file_path):
        return CodeEditIntent(
            status="blocked",
            file_path=file_path,
            reason="only workspace/ paths are allowed for natural-language repo edit intent",
        )

    old_text, new_text = _extract_replace_pair(task_text)

    if old_text is None or new_text is None:
        return CodeEditIntent(
            status="blocked",
            file_path=file_path,
            reason="no explicit replace pair found",
        )

    return CodeEditIntent(
        status="ready",
        file_path=file_path,
        mode="replace_text",
        old_text=old_text,
        new_text=new_text,
        reason="safe single-file workspace replace_text intent",
    )


def build_repo_edit_payload(intent: CodeEditIntent) -> dict:
    return intent.to_payload()


__all__ = ["CodeEditIntent", "parse_code_edit_intent", "build_repo_edit_payload"]