from __future__ import annotations

import pathlib
from typing import Any


PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def to_runtime_safe_schema(
    value: Any,
    *,
    _visited: set[int] | None = None,
    _depth: int = 0,
    _max_depth: int = 12,
):
    if _visited is None:
        _visited = set()

    if _depth > _max_depth:
        return "<max_depth>"

    if isinstance(value, PRIMITIVE_TYPES):
        return value

    object_id = id(value)

    if object_id in _visited:
        return "<recursive>"

    _visited.add(object_id)

    try:
        if isinstance(value, pathlib.Path):
            return str(value)

        if isinstance(value, dict):
            normalized = {}

            for key, item in value.items():
                normalized[str(key)] = to_runtime_safe_schema(
                    item,
                    _visited=_visited,
                    _depth=_depth + 1,
                    _max_depth=_max_depth,
                )

            return normalized

        if isinstance(value, (list, tuple, set)):
            return [
                to_runtime_safe_schema(
                    item,
                    _visited=_visited,
                    _depth=_depth + 1,
                    _max_depth=_max_depth,
                )
                for item in value
            ]

        if isinstance(value, BaseException):
            return {
                "type": value.__class__.__name__,
                "message": str(value),
            }

        return repr(value)

    finally:
        _visited.discard(object_id)