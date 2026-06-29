from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.runtime.runtime_native_mainline import RuntimeNativeMainline


CompatibilityRunner = Callable[[], Any]


def run_via_runtime_native_mainline(
    *,
    entrypoint: str,
    runner: CompatibilityRunner,
    workspace_root: str | Path = "workspace",
    request: dict[str, Any] | None = None,
    goal: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any:
    mainline = RuntimeNativeMainline.with_workspace(workspace_root)
    return mainline.run_compatibility_entry(
        entrypoint=entrypoint,
        runner=runner,
        request=request,
        goal=goal,
        metadata=metadata,
    )
