from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.distributed_worker_evidence_verifier import (
    DistributedWorkerEvidenceVerifier,
)
from core.runtime.runtime_replay_protection import RuntimeReplayProtection


RECORD_TYPES = {
    "snapshot": "execution_plan_snapshot",
    "replay": "execution_replay_record",
    "audit": "execution_audit_record",
    "rollback": "rollback_verification_record",
    "bundle": "runtime_evidence_bundle",
}
TRUSTED_PRODUCER_LAYERS = {"governed_execution", "step_executor"}
VERIFIABLE_PRODUCER_LAYERS = {"distributed_worker"}
SUPPORTED_EVIDENCE_TYPE = "governed_runtime_evidence"


class ImportedEvidenceLoader:
    """Typed loader for external evidence blobs.

    External evidence must pass through this loader before it is handed to
    RuntimeEvidenceConsumer.  Distributed-worker evidence is verified once per
    load operation; the resulting immutable session is then used for validation
    and normalization so nonce consumption cannot drift across repeated verifier
    calls.
    """

    SCHEMA = "zero.runtime.imported_evidence_loader.v1"

    def __init__(
        self,
        *,
        worker_trust_policy: Any | None = None,
        historical_worker_verification: bool = False,
        replay_protection: RuntimeReplayProtection | None = None,
    ) -> None:
        self.worker_verifier = DistributedWorkerEvidenceVerifier(
            worker_trust_policy,
            historical_verification=historical_worker_verification,
            replay_protection=replay_protection,
        )

    def load_records(self, records: Any) -> dict[str, Any]:
        source = copy.deepcopy(records) if isinstance(records, dict) else {}
        loaded: dict[str, Any] = {}
        results: dict[str, Any] = {}
        for slot in RECORD_TYPES:
            result = self.load_record(source.get(slot), expected_slot=slot)
            results[slot] = result
            if isinstance(result.get("record"), dict):
                loaded[slot] = copy.deepcopy(result["record"])
        ok = all(bool(item.get("ok")) for item in results.values())
        return {
            "ok": ok,
            "schema": self.SCHEMA,
            "records": loaded,
            "results": results,
            "invalid_records": [
                slot for slot, result in results.items() if not bool(result.get("ok"))
            ],
        }

    def load_record(self, blob: Any, *, expected_slot: str = "") -> dict[str, Any]:
        slot = _text(expected_slot)
        if slot and slot not in RECORD_TYPES:
            return self._result(
                ok=False,
                classification="invalid_record",
                record=None,
                reasons=["unknown_expected_slot"],
            )
        if not isinstance(blob, dict):
            return self._result(
                ok=False,
                classification="invalid_record",
                record=None,
                reasons=["unsupported_blob_type"],
            )

        payload = copy.deepcopy(blob)
        classification = self._classify(payload)
        worker_verification = self._verify_worker_once(payload)
        reasons = self._validation_reasons(
            payload,
            expected_slot=slot,
            worker_verification=worker_verification,
        )
        ok = not reasons
        if ok:
            record = self._normalized_record(
                payload,
                classification=classification,
                worker_verification=worker_verification,
            )
        else:
            record = self._rejected_record(
                payload,
                classification=classification,
                reasons=reasons,
                worker_verification=worker_verification,
            )
        return self._result(
            ok=ok,
            classification=classification,
            record=record,
            reasons=reasons,
        )

    def _classify(self, payload: dict[str, Any]) -> str:
        evidence_type = _text(payload.get("evidence_type"))
        artifact_class = _text(payload.get("artifact_class"))
        producer_layer = _text(payload.get("producer_layer"))
        if (
            evidence_type == "output_artifact"
            or artifact_class == "output_artifact"
            or producer_layer == "output_artifact"
        ):
            return "output_artifact"
        if evidence_type == SUPPORTED_EVIDENCE_TYPE:
            if producer_layer == "step_executor":
                return "step_executor_execution_evidence"
            if producer_layer == "governed_execution":
                return "governed_execution_evidence"
            return "external_imported_record"
        if evidence_type or artifact_class or producer_layer or payload.get("record_type"):
            return "external_imported_record"
        return "invalid_record"

    def _verify_worker_once(self, payload: dict[str, Any]) -> dict[str, Any]:
        if _text(payload.get("producer_layer")) not in VERIFIABLE_PRODUCER_LAYERS:
            return {}
        return self.worker_verifier.verify(payload, consume_replay=True)

    def _validation_reasons(
        self,
        payload: dict[str, Any],
        *,
        expected_slot: str,
        worker_verification: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        record_type = _text(payload.get("record_type"))
        if not record_type:
            reasons.append("missing_record_type")
        elif expected_slot and record_type != RECORD_TYPES[expected_slot]:
            reasons.append("record_type_mismatch")

        evidence_type = _text(payload.get("evidence_type"))
        artifact_class = _text(payload.get("artifact_class"))
        if not evidence_type:
            reasons.append("missing_evidence_type")
        elif evidence_type != SUPPORTED_EVIDENCE_TYPE:
            reasons.append("unsupported_evidence_type")
        if evidence_type == "output_artifact" or artifact_class == "output_artifact":
            reasons.append("output_artifact_not_execution_evidence")

        producer_layer = _text(payload.get("producer_layer"))
        if not producer_layer:
            reasons.append("missing_producer_layer")
        elif producer_layer in VERIFIABLE_PRODUCER_LAYERS:
            reasons.extend(f"worker_{reason}" for reason in worker_verification.get("reasons", []))
            if worker_verification.get("reasons"):
                reasons.append("unknown_or_untrusted_producer_layer")
        elif producer_layer not in TRUSTED_PRODUCER_LAYERS:
            reasons.append("unknown_or_untrusted_producer_layer")

        if not self._has_provenance(payload):
            reasons.append("missing_provenance")

        validation = _mapping(payload.get("validation") or payload.get("seal_validation"))
        if validation.get("validated") is not True:
            reasons.append("not_validated")
        if validation.get("provenance_checked") is not True:
            reasons.append("provenance_not_checked")
        if validation.get("seal_valid") is not True:
            reasons.append("seal_not_validated")

        return sorted(set(reasons))

    def _normalized_record(
        self,
        payload: dict[str, Any],
        *,
        classification: str,
        worker_verification: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = copy.deepcopy(payload)
        validation = _mapping(normalized.get("validation") or normalized.get("seal_validation"))
        if _text(normalized.get("producer_layer")) == "distributed_worker":
            normalized["distributed_worker"] = self._distributed_worker_metadata(worker_verification)
            normalized["source_producer_layer"] = "distributed_worker"
            normalized["producer_layer"] = "governed_execution"
        normalized["evidence_type"] = SUPPORTED_EVIDENCE_TYPE
        normalized["artifact_class"] = "execution_evidence"
        normalized["normalized"] = True
        normalized["validation"] = {
            **validation,
            "validated": True,
            "provenance_checked": True,
            "seal_valid": True,
            **self._worker_validation_metadata(worker_verification),
        }
        normalized["loader"] = {
            "schema": self.SCHEMA,
            "classification": classification,
            "verification_session_model": "verify_once",
            "loader_fingerprint": self._fingerprint(normalized),
        }
        return normalized

    def _rejected_record(
        self,
        payload: dict[str, Any],
        *,
        classification: str,
        reasons: list[str],
        worker_verification: dict[str, Any],
    ) -> dict[str, Any]:
        rejected = copy.deepcopy(payload)
        rejected["normalized"] = False
        rejected["loader"] = {
            "schema": self.SCHEMA,
            "classification": classification,
            "verification_session_model": "verify_once",
            "rejected": True,
            "reasons": list(reasons),
            "worker_verification": copy.deepcopy(worker_verification) if worker_verification else {},
        }
        return rejected

    def _distributed_worker_metadata(self, worker_verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "worker_id": worker_verification.get("worker_id", ""),
            "payload_digest": worker_verification.get("payload_digest", ""),
            "signature_algorithm": worker_verification.get("signature_algorithm", ""),
            "trusted_worker": bool(worker_verification.get("trusted_worker")),
            "policy_id": worker_verification.get("policy_id", ""),
            "policy_version": worker_verification.get("policy_version", ""),
            "policy_store_schema": worker_verification.get("policy_store_schema", ""),
            "worker_state": worker_verification.get("worker_state", ""),
            "rotation": copy.deepcopy(worker_verification.get("rotation", {})),
            "replay_protection": copy.deepcopy(worker_verification.get("replay_protection", {})),
        }

    def _worker_validation_metadata(self, worker_verification: dict[str, Any]) -> dict[str, Any]:
        if not worker_verification:
            return {}
        replay = _mapping(worker_verification.get("replay_protection"))
        return {
            "worker_signature_valid": bool(worker_verification.get("signature_valid")),
            "worker_id": worker_verification.get("worker_id", ""),
            "worker_payload_digest": worker_verification.get("payload_digest", ""),
            "worker_policy_id": worker_verification.get("policy_id", ""),
            "worker_policy_version": worker_verification.get("policy_version", ""),
            "worker_nonce": replay.get("nonce", ""),
            "worker_timestamp": replay.get("timestamp", ""),
        }

    def _has_provenance(self, payload: dict[str, Any]) -> bool:
        provenance = payload.get("provenance")
        if isinstance(provenance, dict):
            return bool(_text(provenance.get("source") or provenance.get("source_uri")))
        return bool(_text(payload.get("source") or payload.get("source_uri")))

    def _result(
        self,
        *,
        ok: bool,
        classification: str,
        record: Any,
        reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "schema": self.SCHEMA,
            "classification": classification,
            "record": copy.deepcopy(record),
            "reasons": list(reasons),
        }

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("loader", None)
        encoded = json.dumps(safe, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_imported_evidence_record(blob: Any, *, expected_slot: str = "") -> dict[str, Any]:
    return ImportedEvidenceLoader().load_record(blob, expected_slot=expected_slot)


def load_imported_evidence_records(records: Any) -> dict[str, Any]:
    return ImportedEvidenceLoader().load_records(records)


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "ImportedEvidenceLoader",
    "load_imported_evidence_record",
    "load_imported_evidence_records",
]
