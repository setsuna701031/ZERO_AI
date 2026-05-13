from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ControlledMutationRejected(RuntimeError):
    pass


class ControlledMutationAction:
    ALLOWED_PHASES = {
        "planned",
        "applied",
        "verified",
        "rollback_planned",
        "rolled_back",
        "failed",
        "blocked",
    }

    def __init__(
        self,
        action_id: str,
        boundary_id: str,
        mutation_id: str,
        phase: str,
        sequence: int,
        result: Any = None,
        error: Any = None,
        reason: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._action_id = self._validate_text("action_id", action_id)
        self._boundary_id = self._validate_text("boundary_id", boundary_id)
        self._mutation_id = self._validate_text("mutation_id", mutation_id)
        self._phase = self._validate_phase(phase)
        self._sequence = self._validate_sequence(sequence)
        self._result = copy.deepcopy(result)
        self._error = copy.deepcopy(error)
        self._reason = copy.deepcopy(reason)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._rollback_refs = copy.deepcopy(rollback_refs)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def action_id(self) -> str:
        return self._action_id

    @property
    def boundary_id(self) -> str:
        return self._boundary_id

    @property
    def mutation_id(self) -> str:
        return self._mutation_id

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def result(self) -> Any:
        return copy.deepcopy(self._result)

    @property
    def error(self) -> Any:
        return copy.deepcopy(self._error)

    @property
    def reason(self) -> Any:
        return copy.deepcopy(self._reason)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def evidence_refs(self) -> Any:
        return copy.deepcopy(self._evidence_refs)

    @property
    def rollback_refs(self) -> Any:
        return copy.deepcopy(self._rollback_refs)

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._fingerprint_payload(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "action_id": self._action_id,
            "boundary_id": self._boundary_id,
            "mutation_id": self._mutation_id,
            "phase": self._phase,
            "sequence": self._sequence,
            "result": self._result,
            "error": self._error,
            "reason": self._reason,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "evidence_refs": self._evidence_refs,
            "rollback_refs": self._rollback_refs,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationRejected(
                f"controlled mutation {field_name} is required"
            )
        return value

    def _validate_phase(self, phase: str) -> str:
        phase = self._validate_text("phase", phase)
        if phase not in self.ALLOWED_PHASES:
            raise ControlledMutationRejected(
                f"controlled mutation phase is unsupported: {phase}"
            )
        return phase

    def _validate_sequence(self, sequence: int) -> int:
        if not isinstance(sequence, int) or sequence < 1:
            raise ControlledMutationRejected(
                "controlled mutation sequence must be a positive integer"
            )
        return sequence


class ControlledMutationResult:
    def __init__(self, action: ControlledMutationAction) -> None:
        if not isinstance(action, ControlledMutationAction):
            raise ControlledMutationRejected(
                "controlled mutation result requires ControlledMutationAction"
            )
        self._action = copy.deepcopy(action)

    @property
    def action(self) -> ControlledMutationAction:
        return copy.deepcopy(self._action)

    @property
    def mutation_id(self) -> str:
        return self._action.mutation_id

    @property
    def phase(self) -> str:
        return self._action.phase

    @property
    def sequence(self) -> int:
        return self._action.sequence

    @property
    def action_fingerprint(self) -> str:
        return self._action.fingerprint

    @property
    def fingerprint(self) -> str:
        return self._action.fingerprint


class ControlledMutationBoundary:
    def __init__(self, boundary_id: str) -> None:
        self.boundary_id = self._validate_text("boundary_id", boundary_id)
        self._sequence = 0
        self._actions: list[ControlledMutationAction] = []

    def plan_mutation(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="planned",
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_apply(
        self,
        mutation_id: str,
        result: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="applied",
            mutation_id=mutation_id,
            result=result,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_verify(
        self,
        mutation_id: str,
        result: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="verified",
            mutation_id=mutation_id,
            result=result,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_rollback_plan(
        self,
        mutation_id: str,
        reason: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="rollback_planned",
            mutation_id=mutation_id,
            reason=reason,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_rollback(
        self,
        mutation_id: str,
        result: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="rolled_back",
            mutation_id=mutation_id,
            result=result,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_failure(
        self,
        mutation_id: str,
        error: Any,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="failed",
            mutation_id=mutation_id,
            error=error,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def record_blocked(
        self,
        mutation_id: str,
        reason: Any,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self._record_action(
            phase="blocked",
            mutation_id=mutation_id,
            reason=reason,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def list_actions(self) -> list[ControlledMutationAction]:
        return copy.deepcopy(self._actions)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "boundary_id": self.boundary_id,
                "action_fingerprints": [
                    action.fingerprint
                    for action in self._actions
                ],
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _record_action(
        self,
        phase: str,
        mutation_id: str,
        result: Any = None,
        error: Any = None,
        reason: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        mutation_id = self._validate_text("mutation_id", mutation_id)
        self._sequence += 1
        action = ControlledMutationAction(
            action_id=self._action_id(
                mutation_id=mutation_id,
                phase=phase,
                sequence=self._sequence,
            ),
            boundary_id=self.boundary_id,
            mutation_id=mutation_id,
            phase=phase,
            sequence=self._sequence,
            result=result,
            error=error,
            reason=reason,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )
        self._actions.append(copy.deepcopy(action))
        return ControlledMutationResult(action)

    def _action_id(self, mutation_id: str, phase: str, sequence: int) -> str:
        return f"{self.boundary_id}:{mutation_id}:{phase}:{sequence}"

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationRejected(
                f"controlled mutation boundary {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationAction",
    "ControlledMutationBoundary",
    "ControlledMutationRejected",
    "ControlledMutationResult",
]
