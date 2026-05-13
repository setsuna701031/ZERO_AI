from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.controlled_mutation_sandbox_plan import ControlledMutationSandboxPlan


class ControlledMutationSandboxExecutorRejected(RuntimeError):
    pass


class ControlledMutationSandboxExecutionRecord:
    def __init__(
        self,
        record_id: str,
        executor_id: str,
        sandbox_id: str,
        mutation_id: str,
        execution_phase: str,
        sequence: int,
        target_paths: Any = None,
        patch_identity: Any = None,
        verification_result: Any = None,
        rollback_result: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._record_id = self._validate_text("record_id", record_id)
        self._executor_id = self._validate_text("executor_id", executor_id)
        self._sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        self._mutation_id = self._validate_text("mutation_id", mutation_id)
        self._execution_phase = self._validate_text("execution_phase", execution_phase)
        self._sequence = self._validate_sequence(sequence)
        self._target_paths = self._normalize_target_paths(target_paths)
        self._patch_identity = copy.deepcopy(patch_identity)
        self._verification_result = copy.deepcopy(verification_result)
        self._rollback_result = copy.deepcopy(rollback_result)
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def record_id(self) -> str:
        return self._record_id

    @property
    def executor_id(self) -> str:
        return self._executor_id

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @property
    def mutation_id(self) -> str:
        return self._mutation_id

    @property
    def execution_phase(self) -> str:
        return self._execution_phase

    @property
    def target_paths(self) -> list[str]:
        return copy.deepcopy(self._target_paths)

    @property
    def patch_identity(self) -> Any:
        return copy.deepcopy(self._patch_identity)

    @property
    def verification_result(self) -> Any:
        return copy.deepcopy(self._verification_result)

    @property
    def rollback_result(self) -> Any:
        return copy.deepcopy(self._rollback_result)

    @property
    def evidence_refs(self) -> Any:
        return copy.deepcopy(self._evidence_refs)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def sequence(self) -> int:
        return self._sequence

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
            "record_id": self._record_id,
            "executor_id": self._executor_id,
            "sandbox_id": self._sandbox_id,
            "mutation_id": self._mutation_id,
            "execution_phase": self._execution_phase,
            "target_paths": self._target_paths,
            "patch_identity": self._patch_identity,
            "verification_result": self._verification_result,
            "rollback_result": self._rollback_result,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "sequence": self._sequence,
        }

    def _normalize_target_paths(self, target_paths: Any) -> list[str]:
        if target_paths is None:
            return []
        if isinstance(target_paths, str):
            paths = [target_paths]
        else:
            try:
                paths = list(target_paths)
            except TypeError as exc:
                raise ControlledMutationSandboxExecutorRejected(
                    "controlled mutation sandbox executor target_paths must be iterable"
                ) from exc

        normalized: set[str] = set()
        for path in paths:
            clean_path = str(path or "").strip()
            if clean_path:
                normalized.add(clean_path)
        return sorted(normalized)

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationSandboxExecutorRejected(
                f"controlled mutation sandbox executor {field_name} is required"
            )
        return value

    def _validate_sequence(self, sequence: int) -> int:
        if not isinstance(sequence, int) or sequence < 1:
            raise ControlledMutationSandboxExecutorRejected(
                "controlled mutation sandbox executor sequence must be positive"
            )
        return sequence


class ControlledMutationSandboxExecutor:
    def __init__(
        self,
        executor_id: str,
        plan: ControlledMutationSandboxPlan,
    ) -> None:
        self.executor_id = self._validate_text("executor_id", executor_id)
        if not isinstance(plan, ControlledMutationSandboxPlan):
            raise ControlledMutationSandboxExecutorRejected(
                "controlled mutation sandbox executor requires ControlledMutationSandboxPlan"
            )
        self.plan = plan
        self._sequence = 0
        self._records: list[ControlledMutationSandboxExecutionRecord] = []

    def record_workspace_copy(
        self,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "workspace_copy",
            target_paths=target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_patch_prepare(
        self,
        patch_identity: Any = None,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "patch_prepare",
            target_paths=target_paths,
            patch_identity=patch_identity,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_patch_apply(
        self,
        patch_identity: Any = None,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "patch_apply",
            target_paths=target_paths,
            patch_identity=patch_identity,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_prepare(
        self,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "verification_prepare",
            target_paths=target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_result(
        self,
        verification_result: Any,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "verification_result",
            target_paths=target_paths,
            verification_result=verification_result,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_prepare(
        self,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "rollback_prepare",
            target_paths=target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_result(
        self,
        rollback_result: Any,
        target_paths: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        return self._record(
            "rollback_result",
            target_paths=target_paths,
            rollback_result=rollback_result,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_records(self) -> list[ControlledMutationSandboxExecutionRecord]:
        return copy.deepcopy(self._records)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "executor_id": self.executor_id,
                "plan_fingerprint": self.plan.fingerprint,
                "record_fingerprints": [
                    record.fingerprint
                    for record in self._records
                ],
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _record(
        self,
        execution_phase: str,
        target_paths: Any = None,
        patch_identity: Any = None,
        verification_result: Any = None,
        rollback_result: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationSandboxExecutionRecord:
        self._sequence += 1
        record = ControlledMutationSandboxExecutionRecord(
            record_id=self._record_id(execution_phase, self._sequence),
            executor_id=self.executor_id,
            sandbox_id=self.plan.sandbox_id,
            mutation_id=self.plan.mutation_id,
            execution_phase=execution_phase,
            sequence=self._sequence,
            target_paths=self.plan.target_paths if target_paths is None else target_paths,
            patch_identity=self.plan.patch_identity if patch_identity is None else patch_identity,
            verification_result=verification_result,
            rollback_result=rollback_result,
            evidence_refs=self.plan.evidence_refs if evidence_refs is None else evidence_refs,
            metadata=self.plan.metadata if metadata is None else metadata,
            runtime_args=self.plan.runtime_args if runtime_args is None else runtime_args,
        )
        self._records.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    def _record_id(self, execution_phase: str, sequence: int) -> str:
        return (
            f"{self.executor_id}:{self.plan.sandbox_id}:"
            f"{self.plan.mutation_id}:{execution_phase}:{sequence}"
        )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationSandboxExecutorRejected(
                f"controlled mutation sandbox executor {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationSandboxExecutionRecord",
    "ControlledMutationSandboxExecutor",
    "ControlledMutationSandboxExecutorRejected",
]
