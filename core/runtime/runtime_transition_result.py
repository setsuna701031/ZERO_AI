"""Canonical runtime transition result.

This module provides one result wrapper for transition contract, enforcement,
guard, lifecycle, replay, and recovery callers.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_transition_evidence import (
    RuntimeTransitionEvidence,
    build_runtime_transition_evidence,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord


RUNTIME_TRANSITION_RESULT_SCHEMA = "runtime_transition_result.v1"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class RuntimeTransitionResult:
    record: RuntimeTransitionRecord
    evidence: RuntimeTransitionEvidence
    schema: str = RUNTIME_TRANSITION_RESULT_SCHEMA
    status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        status = _clean_text(self.status or self.record.status)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "metadata", copy.deepcopy(dict(self.metadata or {})))

    @property
    def ok(self) -> bool:
        return self.record.ok and self.evidence.blocked is not True

    @property
    def allowed(self) -> bool:
        return self.record.allowed

    @property
    def blocked(self) -> bool:
        return bool(self.record.blocked)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "ok": self.ok,
            "allowed": self.allowed,
            "blocked": self.blocked,
            "record": self.record.to_dict(),
            "evidence": self.evidence.to_dict(),
            "metadata": copy.deepcopy(self.metadata),
        }


def build_runtime_transition_result(
    record: RuntimeTransitionRecord | dict[str, Any],
    *,
    evidence: RuntimeTransitionEvidence | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransitionResult:
    transition_record = (
        record
        if isinstance(record, RuntimeTransitionRecord)
        else RuntimeTransitionRecord.from_mapping(record)
    )
    transition_evidence = evidence or build_runtime_transition_evidence(transition_record)

    return RuntimeTransitionResult(
        record=transition_record,
        evidence=transition_evidence,
        status=status or transition_record.status,
        metadata=metadata or {},
    )


def runtime_transition_result_from_parts(
    *,
    record: RuntimeTransitionRecord,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransitionResult:
    return build_runtime_transition_result(
        record,
        status=status,
        metadata=metadata,
    )
