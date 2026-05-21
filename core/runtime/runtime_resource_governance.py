from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from core.runtime.runtime_events import RuntimeEvent


DEFAULT_RUNTIME_BUDGETS = {
    "execution": 100,
    "mutation": 20,
    "retry": 5,
    "recovery": 3,
    "verification": 20,
    "replay": 5,
}


@dataclass(frozen=True)
class RuntimeBudgetSnapshot:
    limits: dict[str, int]
    used: dict[str, int]
    exhausted: tuple[str, ...] = ()

    def remaining(self, budget: str) -> int:
        return int(self.limits.get(budget, 0)) - int(self.used.get(budget, 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "limits": dict(self.limits),
            "used": dict(self.used),
            "remaining": {
                key: self.remaining(key)
                for key in sorted(set(self.limits) | set(self.used))
            },
            "exhausted": list(self.exhausted),
        }


class RuntimeBudgetExceeded(RuntimeError):
    def __init__(self, budget: str, snapshot: RuntimeBudgetSnapshot) -> None:
        self.budget = budget
        self.snapshot = snapshot
        super().__init__(f"runtime_budget_exhausted:{budget}")


class BudgetExhaustedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        budget: str,
        snapshot: RuntimeBudgetSnapshot,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="BudgetExhaustedEvent",
            payload={"budget": budget, "snapshot": snapshot.to_dict()},
            metadata=metadata or {},
            sequence=sequence,
        )


@dataclass(frozen=True)
class RuntimeResourceGovernor:
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_RUNTIME_BUDGETS))
    used: dict[str, int] = field(default_factory=dict)

    def consume(self, budget: str, amount: int = 1) -> "RuntimeResourceGovernor":
        clean_budget = str(budget or "").strip().lower()
        if not clean_budget:
            raise ValueError("runtime_budget_name_required")
        if amount < 0:
            raise ValueError("runtime_budget_amount_negative")
        limits = dict(self.limits)
        if clean_budget not in limits:
            limits[clean_budget] = amount
        used = dict(self.used)
        used[clean_budget] = int(used.get(clean_budget, 0)) + int(amount)
        updated = replace(self, limits=limits, used=used)
        snapshot = updated.snapshot()
        if snapshot.remaining(clean_budget) < 0:
            raise RuntimeBudgetExceeded(clean_budget, snapshot)
        return updated

    def snapshot(self) -> RuntimeBudgetSnapshot:
        exhausted = tuple(
            sorted(
                budget
                for budget in set(self.limits) | set(self.used)
                if int(self.used.get(budget, 0)) >= int(self.limits.get(budget, 0))
            )
        )
        return RuntimeBudgetSnapshot(
            limits=dict(self.limits),
            used=dict(self.used),
            exhausted=exhausted,
        )


__all__ = [
    "BudgetExhaustedEvent",
    "DEFAULT_RUNTIME_BUDGETS",
    "RuntimeBudgetExceeded",
    "RuntimeBudgetSnapshot",
    "RuntimeResourceGovernor",
]
