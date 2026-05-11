from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping


def safe_deepcopy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return make_json_safe(value)


def make_json_safe(value: Any, _seen: set[int] | None = None) -> Any:
    if _seen is None:
        _seen = set()

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, BaseException):
        return {
            "error_type": value.__class__.__name__,
            "error": str(value),
        }
    if isinstance(value, Path):
        return str(value)

    value_id = id(value)
    if value_id in _seen:
        return "<circular_ref>"

    if isinstance(value, Mapping):
        _seen.add(value_id)
        try:
            return {str(key): make_json_safe(item, _seen) for key, item in value.items()}
        finally:
            _seen.discard(value_id)

    if isinstance(value, (list, tuple, set)):
        _seen.add(value_id)
        try:
            return [make_json_safe(item, _seen) for item in value]
        finally:
            _seen.discard(value_id)

    if hasattr(value, "__dict__"):
        _seen.add(value_id)
        try:
            return {
                "object_type": value.__class__.__name__,
                "attributes": make_json_safe(vars(value), _seen),
            }
        except Exception:
            return str(value)
        finally:
            _seen.discard(value_id)

    return str(value)


def freeze_runtime_export(value: Any) -> Any:
    return make_json_safe(safe_deepcopy(value))


def clone_runtime_export(value: Any) -> Any:
    return safe_deepcopy(freeze_runtime_export(value))
