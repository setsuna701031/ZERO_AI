"""ZERO engineering memory layer.

This package persists and queries records only. It owns no runtime, scheduling,
planning, decision-making, or automatic repair behavior.
"""

from core.memory.decision_memory import DecisionMemory
from core.memory.engineering_memory import EngineeringMemory
from core.memory.issue_memory import IssueMemory
from core.memory.memory_contract import MEMORY_SCHEMA, MemoryContract, MemoryRecord, MemoryType
from core.memory.memory_query import MemoryQuery
from core.memory.memory_repository import MemoryRepository
from core.memory.memory_ownership_contract import (
    audit_memory_control_boundaries,
    memory_architecture_summary,
)
from core.memory.task_memory import TaskMemory
from core.memory.work_package_memory import (
    WorkPackageMemoryError,
    WorkPackageMemoryRecord,
    WorkPackageMemoryStore,
)

__all__ = [
    "MEMORY_SCHEMA",
    "DecisionMemory",
    "EngineeringMemory",
    "IssueMemory",
    "MemoryContract",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryRepository",
    "MemoryType",
    "TaskMemory",
    "WorkPackageMemoryError",
    "WorkPackageMemoryRecord",
    "WorkPackageMemoryStore",
    "audit_memory_control_boundaries",
    "memory_architecture_summary",
]
