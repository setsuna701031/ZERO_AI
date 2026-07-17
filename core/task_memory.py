"""Deprecated compatibility import for legacy ``core.task_memory`` callers.

Use ``core.memory.task_memory`` for the canonical memory records. This module
owns no runtime lifecycle or execution behavior.
"""

from core.memory.task_memory import TaskMemory


DEPRECATED_MEMORY_PATH = "core.task_memory"
CANONICAL_MEMORY_PATH = "core.memory.task_memory"

__all__ = ["CANONICAL_MEMORY_PATH", "DEPRECATED_MEMORY_PATH", "TaskMemory"]
