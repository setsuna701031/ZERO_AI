from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from core.runtime.runtime_trust_policy import RuntimeTrustPolicy, load_runtime_trust_policy


class RuntimeTrustPolicyStore:
    """Managed load/validation boundary for runtime trust policies.

    The store owns policy ingress and rotation-aware worker lookup.  Callers get
    an immutable lookup envelope instead of relying on raw policy internals.
    """

    SCHEMA = "zero.runtime.trust_policy_store.v1"

    def __init__(
        self,
        source: Any = None,
        *,
        allow_retired_for_historical: bool = False,
    ) -> None:
        self.source = source
        self.allow_retired_for_historical = bool(allow_retired_for_historical)
        self.policy = load_runtime_trust_policy(
            source,
            allow_retired_for_historical=self.allow_retired_for_historical,
        )
        self._validation = self._build_validation()

    @property
    def validation(self) -> dict[str, Any]:
        return copy.deepcopy(self._validation)

    @property
    def ok(self) -> bool:
        return bool(self._validation.get("ok"))

    def lookup_worker(self, worker_id: str, *, historical: bool = False) -> dict[str, Any]:
        worker_id_text = _text(worker_id)
        material = self.policy.worker_material(worker_id_text, historical=historical)
        reasons = list(material.get("reasons", []))
        ok = bool(material.get("ok")) and self.ok
        if not self.ok:
            reasons.extend(f"policy_{reason}" for reason in self._validation.get("reasons", []))
            ok = False
        return {
            **copy.deepcopy(material),
            "ok": ok,
            "worker_id": worker_id_text,
            "policy_id": self._validation.get("policy_id", ""),
            "policy_version": self._validation.get("policy_version", ""),
            "store_schema": self.SCHEMA,
            "managed_store": True,
            "historical_lookup": bool(historical),
            "allow_retired_for_historical": self.allow_retired_for_historical,
            "source_kind": self._source_kind(),
            "reasons": sorted(set(reasons)),
        }

    def policy_identity(self) -> dict[str, Any]:
        return {
            "store_schema": self.SCHEMA,
            "managed_store": True,
            "source_kind": self._source_kind(),
            "policy_id": self._validation.get("policy_id", ""),
            "policy_version": self._validation.get("policy_version", ""),
            "ok": self.ok,
        }

    def _build_validation(self) -> dict[str, Any]:
        validation = copy.deepcopy(self.policy.validation)
        return {
            **validation,
            "store_schema": self.SCHEMA,
            "managed_store": True,
            "source_kind": self._source_kind(),
        }

    def _source_kind(self) -> str:
        if isinstance(self.source, RuntimeTrustPolicy):
            return "runtime_trust_policy"
        if isinstance(self.source, dict):
            return "mapping"
        if isinstance(self.source, (str, Path)):
            return "file"
        if self.source is None:
            return "missing"
        return type(self.source).__name__


def load_runtime_trust_policy_store(
    source: Any,
    *,
    allow_retired_for_historical: bool = False,
) -> RuntimeTrustPolicyStore:
    return RuntimeTrustPolicyStore(
        source,
        allow_retired_for_historical=allow_retired_for_historical,
    )


def validate_runtime_trust_policy_store(source: Any) -> dict[str, Any]:
    return RuntimeTrustPolicyStore(source).validation


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "RuntimeTrustPolicyStore",
    "load_runtime_trust_policy_store",
    "validate_runtime_trust_policy_store",
]
