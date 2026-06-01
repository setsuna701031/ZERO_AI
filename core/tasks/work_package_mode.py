from __future__ import annotations

from enum import Enum


class WorkPackageMode(str, Enum):
    EXPLORE = "explore"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"


__all__ = ["WorkPackageMode"]
