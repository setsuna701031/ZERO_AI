from __future__ import annotations
from typing import Any
from core.engineering.engineering_execution_session import validate_engineering_execution_session

def validate_execution_session(value: Any) -> Any:
    return validate_engineering_execution_session(value)

__all__ = ["validate_execution_session", "validate_engineering_execution_session"]
