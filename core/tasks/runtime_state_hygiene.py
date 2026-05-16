from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any, Mapping


def safe_deepcopy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return make_json_safe(value)


def _child_path(parent: str, key: Any, *, sequence: bool = False) -> str:
    if sequence:
        return f"{parent}[{key}]"
    key_text = str(key)
    if key_text.isidentifier():
        return f"{parent}.{key_text}"
    return f"{parent}[{key_text!r}]"


def make_json_safe(value: Any, _seen: dict[int, str] | None = None, _path: str = "$") -> Any:
    if _seen is None:
        _seen = {}

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
        return f"<circular-ref:{_seen[value_id]}>"

    if isinstance(value, Mapping):
        _seen[value_id] = _path
        try:
            return {
                str(key): make_json_safe(item, _seen, _child_path(_path, key))
                for key, item in value.items()
            }
        finally:
            _seen.pop(value_id, None)

    if isinstance(value, (list, tuple, set)):
        _seen[value_id] = _path
        try:
            return [
                make_json_safe(item, _seen, _child_path(_path, index, sequence=True))
                for index, item in enumerate(value)
            ]
        finally:
            _seen.pop(value_id, None)

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        _seen[value_id] = _path
        try:
            return {
                "object_type": value.__class__.__name__,
                "attributes": {
                    field.name: make_json_safe(
                        getattr(value, field.name),
                        _seen,
                        _child_path(_path, field.name),
                    )
                    for field in dataclasses.fields(value)
                },
            }
        finally:
            _seen.pop(value_id, None)

    if hasattr(value, "__dict__"):
        _seen[value_id] = _path
        try:
            return {
                "object_type": value.__class__.__name__,
                "attributes": make_json_safe(vars(value), _seen, _child_path(_path, "__dict__")),
            }
        except Exception:
            return {
                "object_type": value.__class__.__name__,
                "repr": repr(value),
            }
        finally:
            _seen.pop(value_id, None)

    return {
        "object_type": value.__class__.__name__,
        "repr": repr(value),
    }


def freeze_runtime_export(value: Any) -> Any:
    return make_json_safe(safe_deepcopy(value))


def clone_runtime_export(value: Any) -> Any:
    return safe_deepcopy(freeze_runtime_export(value))
