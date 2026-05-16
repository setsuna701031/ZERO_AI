from __future__ import annotations

import re
from typing import Dict, Optional


COMMAND_PREFIX_PATTERNS = (
    r"^cmd\s*:\s*(.+)$",
    r"^run\s*:\s*(.+)$",
    r"^run\s+(.+)$",
    r"^command\s*:\s*(.+)$",
    r"^command\s+(.+)$",
    r"^execute\s+(.+)$",
    r"^shell\s+(.+)$",
    r"^bash\s+(.+)$",
)

COMMAND_START_PREFIXES = (
    "python ",
    "py ",
    "cmd /c ",
    "powershell ",
)


def try_plan_command(text: str) -> Optional[Dict[str, str]]:
    stripped = str(text or "").strip()
    if not stripped:
        return None

    for pattern in COMMAND_PREFIX_PATTERNS:
        match = re.match(pattern, stripped, flags=re.IGNORECASE)
        if not match:
            continue
        command = match.group(1).strip()
        if command:
            return {"type": "command", "command": command}

    lowered = stripped.lower()
    if lowered.startswith(COMMAND_START_PREFIXES):
        return {"type": "command", "command": stripped}

    return None
