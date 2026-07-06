from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


RUNTIME_OPERATOR_CONFIG_SCHEMA = "zero.runtime.operator_config.v1"


@dataclass(frozen=True)
class RuntimeOperatorConfig:
    runtime_mode: str = "manual"
    max_tick_limit: int = 1
    checkpoint_path: str = "workspace/runtime/operator_checkpoint.json"
    auto_resume_enabled: bool = False
    emergency_stop_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema"] = RUNTIME_OPERATOR_CONFIG_SCHEMA
        return data


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return value is True


def load_runtime_operator_config(source: Any = None) -> RuntimeOperatorConfig:
    if source is None:
        return RuntimeOperatorConfig()

    if isinstance(source, RuntimeOperatorConfig):
        return source

    data: Mapping[str, Any]
    if isinstance(source, Mapping):
        data = source
    else:
        path = Path(str(source))
        if not path.exists():
            return RuntimeOperatorConfig(checkpoint_path=str(path))
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        data = loaded if isinstance(loaded, Mapping) else {}

    mode = str(data.get("runtime_mode") or "manual").strip().lower()
    if mode not in {"manual", "autonomous"}:
        mode = "manual"

    return RuntimeOperatorConfig(
        runtime_mode=mode,
        max_tick_limit=_positive_int(data.get("max_tick_limit"), 1),
        checkpoint_path=str(
            data.get("checkpoint_path") or "workspace/runtime/operator_checkpoint.json"
        ),
        auto_resume_enabled=_bool(data.get("auto_resume_enabled"), False),
        emergency_stop_enabled=_bool(data.get("emergency_stop_enabled"), True),
    )


__all__ = [
    "RUNTIME_OPERATOR_CONFIG_SCHEMA",
    "RuntimeOperatorConfig",
    "load_runtime_operator_config",
]
