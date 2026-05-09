from __future__ import annotations

from pathlib import Path
from typing import Any


class ExecutionCycleRuntime:
    """
    Scheduler execution-cycle boundary container.

    Phase6 only establishes the runtime boundary.
    No scheduler execution logic is migrated yet.
    """

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root or Path.cwd()).resolve()

    def describe(self) -> dict[str, Any]:
        return {
            "runtime": "execution_cycle_runtime",
            "phase": "phase6_boundary_only",
            "repo_root": str(self.repo_root),
        }


def build_execution_cycle_runtime(
    repo_root: str | Path | None = None,
) -> ExecutionCycleRuntime:
    return ExecutionCycleRuntime(repo_root=repo_root)