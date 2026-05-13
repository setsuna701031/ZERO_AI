from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ControlledMutationSandboxPlanRejected(RuntimeError):
    pass


class ControlledMutationSandboxPlan:
    def __init__(
        self,
        sandbox_id: str,
        mutation_id: str,
        target_paths: Any = None,
        patch_identity: Any = None,
        verification_strategy: Any = None,
        rollback_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self.sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        self.mutation_id = self._validate_text("mutation_id", mutation_id)
        self._target_paths = self._normalize_target_paths(target_paths)
        self._patch_identity = copy.deepcopy(patch_identity)
        self._verification_strategy = copy.deepcopy(verification_strategy)
        self._rollback_strategy = copy.deepcopy(rollback_strategy)
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @classmethod
    def plan_workspace_copy(
        cls,
        sandbox_id: str,
        mutation_id: str,
        target_paths: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> "ControlledMutationSandboxPlan":
        return cls(
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            target_paths=target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def plan_patch_apply(
        self,
        patch_identity: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> "ControlledMutationSandboxPlan":
        self._patch_identity = copy.deepcopy(patch_identity)
        self._merge_optional_fields(
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        return self

    def plan_verification(
        self,
        verification_strategy: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> "ControlledMutationSandboxPlan":
        self._verification_strategy = copy.deepcopy(verification_strategy)
        self._merge_optional_fields(
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        return self

    def plan_rollback_strategy(
        self,
        rollback_strategy: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> "ControlledMutationSandboxPlan":
        self._rollback_strategy = copy.deepcopy(rollback_strategy)
        self._merge_optional_fields(
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        return self

    @property
    def target_paths(self) -> list[str]:
        return copy.deepcopy(self._target_paths)

    @property
    def patch_identity(self) -> Any:
        return copy.deepcopy(self._patch_identity)

    @property
    def verification_strategy(self) -> Any:
        return copy.deepcopy(self._verification_strategy)

    @property
    def rollback_strategy(self) -> Any:
        return copy.deepcopy(self._rollback_strategy)

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
            "sandbox_id": self.sandbox_id,
            "mutation_id": self.mutation_id,
            "target_paths": self._target_paths,
            "patch_identity": self._patch_identity,
            "verification_strategy": self._verification_strategy,
            "rollback_strategy": self._rollback_strategy,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _merge_optional_fields(
        self,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> None:
        if evidence_refs is not None:
            self._evidence_refs = copy.deepcopy(evidence_refs)
        if metadata is not None:
            self._metadata = copy.deepcopy(metadata)
        if runtime_args is not None:
            self._runtime_args = copy.deepcopy(runtime_args)

    def _normalize_target_paths(self, target_paths: Any) -> list[str]:
        if target_paths is None:
            return []
        if isinstance(target_paths, str):
            paths = [target_paths]
        else:
            try:
                paths = list(target_paths)
            except TypeError as exc:
                raise ControlledMutationSandboxPlanRejected(
                    "controlled mutation sandbox target_paths must be iterable"
                ) from exc

        normalized: set[str] = set()
        for path in paths:
            clean_path = str(path or "").strip()
            if clean_path:
                normalized.add(clean_path)
        return sorted(normalized)

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationSandboxPlanRejected(
                f"controlled mutation sandbox {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationSandboxPlan",
    "ControlledMutationSandboxPlanRejected",
]
