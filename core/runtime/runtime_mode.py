from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):
    EXECUTE = "execute"
    REPLAY = "replay"
    AUDIT = "audit"
    REPAIR_REPLAY = "repair_replay"


READONLY_RUNTIME_MODES = {
    RuntimeMode.REPLAY,
    RuntimeMode.AUDIT,
    RuntimeMode.REPAIR_REPLAY,
}