from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_replay_protection import RuntimeReplayProtection
from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore


SIGNATURE_ALGORITHM = "zero-worker-sha256-v1"


@dataclass(frozen=True)
class DistributedWorkerVerificationSession:
    """Immutable verification result for one distributed-worker evidence blob."""

    result: dict[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.result.get("ok"))

    @property
    def reasons(self) -> list[str]:
        return list(self.result.get("reasons", []))

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.result)


class DistributedWorkerEvidenceVerifier:
    """Verify imported evidence emitted by trusted distributed workers.

    The verifier owns exactly one verification session per evidence blob.  It
    checks worker identity, trust-policy lookup, payload digest, deterministic
    signature, and replay freshness/nonce state.  Loader code should consume the
    returned session instead of calling verification repeatedly.
    """

    SCHEMA = "zero.runtime.distributed_worker_evidence_verifier.v1"

    def __init__(
        self,
        trusted_workers: Any | None = None,
        *,
        historical_verification: bool = False,
        replay_protection: RuntimeReplayProtection | None = None,
    ) -> None:
        self.historical_verification = bool(historical_verification)
        self.trust_policy_store = (
            trusted_workers
            if isinstance(trusted_workers, RuntimeTrustPolicyStore)
            else RuntimeTrustPolicyStore(
                trusted_workers,
                allow_retired_for_historical=self.historical_verification,
            )
        )
        self.replay_protection = replay_protection or RuntimeReplayProtection()

    def verify(self, evidence: Any, *, consume_replay: bool = True) -> dict[str, Any]:
        return self.verify_session(evidence, consume_replay=consume_replay).as_dict()

    def verify_session(
        self,
        evidence: Any,
        *,
        consume_replay: bool = True,
    ) -> DistributedWorkerVerificationSession:
        payload = copy.deepcopy(evidence) if isinstance(evidence, dict) else {}
        reasons: list[str] = []

        worker_id = _text(payload.get("worker_id"))
        if not worker_id:
            reasons.append("missing_worker_id")

        policy_validation = self.trust_policy_store.validation
        if not policy_validation.get("ok"):
            reasons.extend(f"policy_{reason}" for reason in policy_validation.get("reasons", []))

        worker_material = self.trust_policy_store.lookup_worker(
            worker_id,
            historical=self.historical_verification,
        )
        if worker_id and not worker_material.get("ok"):
            reasons.extend(worker_material.get("reasons", []))

        signature_metadata = _mapping(payload.get("signature_metadata"))
        if not signature_metadata:
            reasons.append("missing_signature_metadata")

        algorithm = _text(signature_metadata.get("algorithm"))
        if signature_metadata and algorithm != SIGNATURE_ALGORITHM:
            reasons.append("unsupported_signature_algorithm")

        signed_digest = _text(
            signature_metadata.get("payload_digest")
            or payload.get("payload_digest")
            or payload.get("signed_payload_digest")
        )
        if signature_metadata and not signed_digest:
            reasons.append("missing_payload_digest")

        signature = _text(signature_metadata.get("signature"))
        if signature_metadata and not signature:
            reasons.append("missing_signature")

        actual_digest = compute_worker_payload_digest(payload)
        if signed_digest and signed_digest != actual_digest:
            reasons.append("payload_digest_mismatch")

        expected_signature = ""
        if worker_material.get("ok") and signed_digest:
            expected_signature = sign_worker_payload_digest(
                worker_id=worker_id,
                trust_key=worker_material["trust_key"],
                payload_digest=signed_digest,
            )
            if signature and signature != expected_signature:
                reasons.append("invalid_signature")

        replay_result = self.replay_protection.verify(payload, consume=False)
        if not replay_result.get("ok"):
            reasons.extend(f"replay_{reason}" for reason in replay_result.get("reasons", []))

        ok = not reasons
        if ok and consume_replay:
            replay_result = self.replay_protection.verify(payload, consume=True)
            if not replay_result.get("ok"):
                reasons.extend(f"replay_{reason}" for reason in replay_result.get("reasons", []))
                ok = False

        result = {
            "ok": ok,
            "schema": self.SCHEMA,
            "session_model": "verify_once",
            "worker_id": worker_id,
            "trusted_worker": bool(worker_material.get("ok")),
            "policy_id": worker_material.get("policy_id", ""),
            "policy_version": worker_material.get("policy_version", ""),
            "policy_store_schema": worker_material.get("store_schema", ""),
            "worker_state": worker_material.get("worker_state", ""),
            "rotation": copy.deepcopy(worker_material.get("rotation", {})),
            "replay_protection": copy.deepcopy(replay_result),
            "signature_algorithm": algorithm,
            "payload_digest": actual_digest,
            "signed_payload_digest": signed_digest,
            "expected_signature": expected_signature,
            "signature_valid": ok,
            "reasons": sorted(set(reasons)),
        }
        return DistributedWorkerVerificationSession(result=result)


def compute_worker_payload_digest(payload: Any) -> str:
    safe = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    for key in (
        "signature_metadata",
        "validation",
        "seal_validation",
        "loader",
        "normalized",
        "payload_digest",
        "signed_payload_digest",
    ):
        safe.pop(key, None)
    encoded = json.dumps(safe, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sign_worker_payload_digest(*, worker_id: str, trust_key: str, payload_digest: str) -> str:
    raw = f"{_text(worker_id)}:{_text(trust_key)}:{_text(payload_digest)}"
    return "worker-signature-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_worker_signature_metadata(
    payload: Any,
    *,
    worker_id: str,
    trust_key: str,
) -> dict[str, str]:
    payload_digest = compute_worker_payload_digest(payload)
    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "payload_digest": payload_digest,
        "signature": sign_worker_payload_digest(
            worker_id=worker_id,
            trust_key=trust_key,
            payload_digest=payload_digest,
        ),
    }


def verify_distributed_worker_evidence(
    evidence: Any,
    *,
    trusted_workers: Any | None = None,
    historical_verification: bool = False,
    replay_protection: RuntimeReplayProtection | None = None,
) -> dict[str, Any]:
    return DistributedWorkerEvidenceVerifier(
        trusted_workers,
        historical_verification=historical_verification,
        replay_protection=replay_protection,
    ).verify(evidence)


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "DistributedWorkerEvidenceVerifier",
    "DistributedWorkerVerificationSession",
    "SIGNATURE_ALGORITHM",
    "build_worker_signature_metadata",
    "compute_worker_payload_digest",
    "sign_worker_payload_digest",
    "verify_distributed_worker_evidence",
]
