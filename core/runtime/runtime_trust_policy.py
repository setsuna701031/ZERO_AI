from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ACTIVE_STATES = {"active", "enabled"}
REVOKED_STATES = {"revoked", "disabled", "blocked"}
RETIRED_STATES = {"retired", "rotated", "expired"}


class RuntimeTrustPolicy:
    """Versioned trust policy for distributed-worker evidence verification."""

    SCHEMA = "zero.runtime.trust_policy.v1"

    def __init__(
        self,
        policy: Any,
        *,
        allow_retired_for_historical: bool = False,
    ) -> None:
        self._policy = copy.deepcopy(policy) if isinstance(policy, dict) else {}
        self.allow_retired_for_historical = bool(allow_retired_for_historical)
        self._validation = self._validate_policy(self._policy)

    @property
    def policy_id(self) -> str:
        return _text(self._policy.get("policy_id"))

    @property
    def policy_version(self) -> str:
        return _text(self._policy.get("policy_version") or self._policy.get("version"))

    @property
    def validation(self) -> dict[str, Any]:
        return copy.deepcopy(self._validation)

    @property
    def ok(self) -> bool:
        return bool(self._validation.get("ok"))

    def worker_material(self, worker_id: str, *, historical: bool = False) -> dict[str, Any]:
        worker = _text(worker_id)
        if not self.ok:
            return self._worker_result(False, worker, "", ["invalid_trust_policy"])
        if not worker:
            return self._worker_result(False, worker, "", ["missing_worker_id"])

        entries = self._worker_entries()
        entry = entries.get(worker)
        if not entry:
            return self._worker_result(False, worker, "", ["unknown_worker_id"])

        state = self._entry_state(entry)
        if state in REVOKED_STATES:
            return self._worker_result(False, worker, "", ["revoked_worker_id"])
        if state in RETIRED_STATES and not (historical or self.allow_retired_for_historical):
            return self._worker_result(False, worker, "", ["retired_trust_material"])

        key = _text(entry.get("trust_key") or entry.get("verifier_material") or entry.get("public_key"))
        if not key:
            return self._worker_result(False, worker, "", ["missing_trust_key"])

        return self._worker_result(
            True,
            worker,
            key,
            [],
            state=state or "active",
            rotation=copy.deepcopy(entry.get("rotation") if isinstance(entry.get("rotation"), dict) else {}),
        )

    def _validate_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        if not policy:
            reasons.append("missing_trust_policy")
        if not (_text(policy.get("policy_id")) or _text(policy.get("policy_version") or policy.get("version"))):
            reasons.append("missing_policy_metadata")

        entries = self._worker_entries(policy)
        if not entries:
            reasons.append("missing_trusted_workers")

        for worker_id, entry in entries.items():
            if not _text(entry.get("worker_id") or worker_id):
                reasons.append("missing_worker_id")
            if not _text(entry.get("trust_key") or entry.get("verifier_material") or entry.get("public_key")):
                reasons.append(f"missing_trust_key:{worker_id}")

        return {
            "ok": not reasons,
            "schema": self.SCHEMA,
            "policy_id": _text(policy.get("policy_id")),
            "policy_version": _text(policy.get("policy_version") or policy.get("version")),
            "worker_count": len(entries),
            "reasons": sorted(set(reasons)),
        }

    def _worker_entries(self, policy: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        source = policy if isinstance(policy, dict) else self._policy
        raw_entries = source.get("trusted_workers") or source.get("workers") or {}
        entries: dict[str, dict[str, Any]] = {}
        if isinstance(raw_entries, dict):
            for worker_id, value in raw_entries.items():
                entry = copy.deepcopy(value) if isinstance(value, dict) else {"trust_key": value}
                entry.setdefault("worker_id", worker_id)
                normalized_id = _text(entry.get("worker_id"))
                if normalized_id:
                    entries[normalized_id] = entry
        elif isinstance(raw_entries, list):
            for value in raw_entries:
                if not isinstance(value, dict):
                    continue
                entry = copy.deepcopy(value)
                normalized_id = _text(entry.get("worker_id"))
                if normalized_id:
                    entries[normalized_id] = entry
        return entries

    def _entry_state(self, entry: dict[str, Any]) -> str:
        rotation = entry.get("rotation") if isinstance(entry.get("rotation"), dict) else {}
        return _text(
            entry.get("status")
            or entry.get("state")
            or rotation.get("state")
            or rotation.get("key_state")
            or "active"
        ).lower()

    def _worker_result(
        self,
        ok: bool,
        worker_id: str,
        trust_key: str,
        reasons: list[str],
        *,
        state: str = "",
        rotation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "worker_id": _text(worker_id),
            "trust_key": _text(trust_key),
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "worker_state": _text(state),
            "rotation": copy.deepcopy(rotation or {}),
            "reasons": sorted(set(reasons)),
        }


def load_runtime_trust_policy(
    source: Any,
    *,
    allow_retired_for_historical: bool = False,
) -> RuntimeTrustPolicy:
    if isinstance(source, (str, Path)):
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        return RuntimeTrustPolicy(
            payload,
            allow_retired_for_historical=allow_retired_for_historical,
        )
    return RuntimeTrustPolicy(
        source,
        allow_retired_for_historical=allow_retired_for_historical,
    )


def validate_runtime_trust_policy(policy: Any) -> dict[str, Any]:
    return RuntimeTrustPolicy(policy).validation


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "RuntimeTrustPolicy",
    "load_runtime_trust_policy",
    "validate_runtime_trust_policy",
]
