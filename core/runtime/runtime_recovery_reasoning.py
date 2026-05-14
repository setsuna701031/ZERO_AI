from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_replay_reconstruction import (
    RuntimeEvidenceReplayReconstructor,
    RuntimeEvidenceReplayState,
)
from core.runtime.runtime_evidence_replay_validation import (
    RuntimeEvidenceReplayValidationReport,
    RuntimeEvidenceReplayValidator,
)


TRUSTED_LINEAGE_TYPES = ("plan", "snapshot", "replay", "audit", "bundle")
FAILED_RECOVERY_STATUSES = {"failed", "error", "exception", "blocked", "denied"}


class RuntimeRecoveryReasoningReport:
    SCHEMA = "zero.runtime.recovery_reasoning.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def replay_trust(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_trust", {}))

    def lineage_trust(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_trust", {}))

    def replay_safety(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_safety", {}))

    def rollback_candidates(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("rollback_candidates", []))

    def failed_execution_recovery(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_recovery", {}))

    def recovery_candidates(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("recovery_candidates", []))

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


class RuntimeRecoveryReasoner:
    """Read-only recovery reasoning over replay validation and lineage state."""

    def __init__(
        self,
        *,
        reconstructor: RuntimeEvidenceReplayReconstructor | None = None,
        validator: RuntimeEvidenceReplayValidator | None = None,
    ) -> None:
        self.reconstructor = reconstructor if reconstructor is not None else RuntimeEvidenceReplayReconstructor()
        self.validator = validator if validator is not None else RuntimeEvidenceReplayValidator(self.reconstructor)

    def reason(self, source: Any) -> RuntimeRecoveryReasoningReport:
        context = self._context(source)
        replay_trust = self._replay_trust_from(context)
        lineage_trust = self._lineage_trust_from(context)
        replay_safety = self._replay_safety_from(context, replay_trust, lineage_trust)
        rollback_candidates = self._rollback_candidates_from(context, replay_safety)
        failed_execution_recovery = self._failed_execution_recovery_from(context, replay_safety)
        recovery_candidates = self._recovery_candidates_from(
            rollback_candidates,
            failed_execution_recovery,
            replay_safety,
        )
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryReasoningReport.SCHEMA,
            "mode": "reasoning_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "replay_fingerprint": context["replay"].fingerprint,
                "validation_fingerprint": context["validation"].fingerprint,
            },
            "replay_trust": replay_trust,
            "lineage_trust": lineage_trust,
            "replay_safety": replay_safety,
            "rollback_candidates": rollback_candidates,
            "failed_execution_recovery": failed_execution_recovery,
            "recovery_candidates": recovery_candidates,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryReasoningReport(payload)

    def analyze_replay_trust(self, source: Any) -> dict[str, Any]:
        return self.reason(source).replay_trust()

    def analyze_lineage_trust(self, source: Any) -> dict[str, Any]:
        return self.reason(source).lineage_trust()

    def classify_replay_safety(self, source: Any) -> dict[str, Any]:
        return self.reason(source).replay_safety()

    def analyze_rollback_candidates(self, source: Any) -> list[dict[str, Any]]:
        return self.reason(source).rollback_candidates()

    def analyze_failed_execution_recovery(self, source: Any) -> dict[str, Any]:
        return self.reason(source).failed_execution_recovery()

    def extract_recovery_candidates(self, source: Any) -> list[dict[str, Any]]:
        return self.reason(source).recovery_candidates()

    def _context(self, source: Any) -> dict[str, Any]:
        replay = self._replay_state(source)
        validation = self.validator.validate(replay)
        return {
            "replay": replay,
            "validation": validation,
            "replay_payload": replay.payload,
            "validation_payload": validation.payload,
        }

    def _replay_state(self, source: Any) -> RuntimeEvidenceReplayState:
        if isinstance(source, RuntimeEvidenceReplayState):
            return RuntimeEvidenceReplayState(source.payload)
        if isinstance(source, RuntimeRecoveryReasoningReport):
            return RuntimeEvidenceReplayState({})
        if isinstance(source, RuntimeEvidenceReplayValidationReport):
            return RuntimeEvidenceReplayState({})
        return self.reconstructor.reconstruct(source)

    def _replay_trust_from(self, context: dict[str, Any]) -> dict[str, Any]:
        replay_payload = self._safe_mapping(context.get("replay_payload"))
        validation = context["validation"]
        sealed_state = self._safe_mapping(replay_payload.get("sealed_state"))
        rollback = self._safe_mapping(replay_payload.get("rollback_replay"))
        replay_linkage = self._safe_mapping(replay_payload.get("replay_linkage"))
        issues = validation.issues()
        issue_types = [self._safe_text(issue.get("type")) for issue in issues if isinstance(issue, dict)]

        score = 0
        if bool(sealed_state.get("sealed", False)):
            score += 30
        if bool(sealed_state.get("complete", False)):
            score += 20
        if validation.ok:
            score += 25
        if bool(replay_linkage.get("verified", False)):
            score += 15
        if bool(rollback.get("verified", False)):
            score += 10

        classification = "untrusted"
        if validation.ok and score >= 90:
            classification = "trusted"
        elif score >= 50 and bool(sealed_state.get("complete", False)):
            classification = "limited"
        elif not bool(sealed_state.get("complete", False)):
            classification = "missing_evidence"

        return {
            "classification": classification,
            "score": score,
            "trusted": classification == "trusted",
            "validation_ok": validation.ok,
            "sealed": bool(sealed_state.get("sealed", False)),
            "complete": bool(sealed_state.get("complete", False)),
            "replay_linkage_verified": bool(replay_linkage.get("verified", False)),
            "rollback_linkage_verified": bool(rollback.get("verified", False)),
            "issue_types": sorted(issue_types),
        }

    def _lineage_trust_from(self, context: dict[str, Any]) -> dict[str, Any]:
        replay_payload = self._safe_mapping(context.get("replay_payload"))
        lineage = self._safe_list(replay_payload.get("lineage_replay"))
        validation_checks = context["validation"].checks()
        lineage_check = self._safe_mapping(validation_checks.get("lineage_consistency"))
        lineage_types = [
            self._safe_text(item.get("lineage_type"))
            for item in lineage
            if isinstance(item, dict)
        ]
        verified_count = sum(
            1
            for item in lineage
            if isinstance(item, dict) and bool(item.get("verified", False))
        )
        expected_prefix = list(TRUSTED_LINEAGE_TYPES[: len(lineage_types)])
        complete = lineage_types == list(TRUSTED_LINEAGE_TYPES)
        ordered = lineage_types == expected_prefix
        verified = bool(lineage) and verified_count == len(lineage)

        if complete and ordered and verified and bool(lineage_check.get("ok", False)):
            classification = "trusted"
        elif lineage and ordered:
            classification = "partial"
        else:
            classification = "untrusted"

        return {
            "classification": classification,
            "trusted": classification == "trusted",
            "lineage_count": len(lineage),
            "verified_count": verified_count,
            "expected_types": list(TRUSTED_LINEAGE_TYPES),
            "actual_types": lineage_types,
            "complete": complete,
            "ordered": ordered,
            "verified": verified,
            "validation_ok": bool(lineage_check.get("ok", False)),
        }

    def _replay_safety_from(
        self,
        context: dict[str, Any],
        replay_trust: dict[str, Any],
        lineage_trust: dict[str, Any],
    ) -> dict[str, Any]:
        validation = context["validation"]
        issues = validation.issues()
        blocking_issue_types = sorted(
            {
                self._safe_text(issue.get("type"))
                for issue in issues
                if isinstance(issue, dict)
            }
        )

        if replay_trust.get("trusted") and lineage_trust.get("trusted") and validation.ok:
            classification = "replay_safe"
            safe = True
        elif replay_trust.get("classification") == "missing_evidence":
            classification = "replay_unsafe_missing_evidence"
            safe = False
        elif validation.ok:
            classification = "replay_safe_limited"
            safe = True
        else:
            classification = "replay_unsafe"
            safe = False

        return {
            "classification": classification,
            "safe": safe,
            "validation_ok": validation.ok,
            "reasoning_only": True,
            "blocking_issue_types": blocking_issue_types,
        }

    def _rollback_candidates_from(
        self,
        context: dict[str, Any],
        replay_safety: dict[str, Any],
    ) -> list[dict[str, Any]]:
        replay_payload = self._safe_mapping(context.get("replay_payload"))
        rollback = self._safe_mapping(replay_payload.get("rollback_replay"))
        validation_checks = context["validation"].checks()
        rollback_check = self._safe_mapping(validation_checks.get("rollback_linkage"))
        if not (
            rollback.get("found")
            and rollback.get("verified")
            and rollback_check.get("ok")
            and replay_safety.get("safe")
        ):
            return []

        candidates = []
        steps = self._safe_list(rollback.get("rollback_steps"))
        for step in steps:
            if not isinstance(step, dict):
                continue
            execution_id = self._safe_text(step.get("execution_id"))
            if not execution_id:
                continue
            candidate = {
                "candidate_id": f"rollback:{self._safe_text(rollback.get('rollback_id'))}:{self._safe_text(step.get('replay_order'))}",
                "candidate_type": "rollback",
                "classification": "rollback_candidate",
                "execution_id": execution_id,
                "rollback_id": self._safe_text(rollback.get("rollback_id")),
                "replay_order": self._safe_int(step.get("replay_order"), 0),
                "safe_to_consider": True,
                "reasoning_only": True,
                "action": "none",
            }
            candidate["fingerprint"] = self._fingerprint(candidate)
            candidates.append(candidate)
        return candidates

    def _failed_execution_recovery_from(
        self,
        context: dict[str, Any],
        replay_safety: dict[str, Any],
    ) -> dict[str, Any]:
        replay_payload = self._safe_mapping(context.get("replay_payload"))
        failed = [
            copy.deepcopy(item)
            for item in self._safe_list(replay_payload.get("failed_execution_replay"))
            if isinstance(item, dict)
        ]
        candidates = []
        for item in failed:
            failed_id = self._safe_text(item.get("failed_execution_id"))
            status = self._safe_text(item.get("status")).lower()
            if not failed_id or status not in FAILED_RECOVERY_STATUSES:
                continue
            candidate = {
                "candidate_id": f"failed_execution:{failed_id}",
                "candidate_type": "failed_execution_replay",
                "classification": "replay_recovery_candidate" if replay_safety.get("safe") else "blocked_recovery_candidate",
                "failed_execution_id": failed_id,
                "status": status,
                "phase": self._safe_text(item.get("phase")),
                "safe_to_consider": bool(replay_safety.get("safe")),
                "reasoning_only": True,
                "action": "none",
            }
            candidate["fingerprint"] = self._fingerprint(candidate)
            candidates.append(candidate)

        classification = "no_failed_execution"
        if candidates and replay_safety.get("safe"):
            classification = "failed_execution_replay_candidates"
        elif candidates:
            classification = "failed_execution_recovery_blocked"

        result = {
            "classification": classification,
            "failed_execution_count": len(failed),
            "candidate_count": len(candidates),
            "safe_to_consider": bool(candidates) and bool(replay_safety.get("safe")),
            "failed_executions": failed,
            "candidates": candidates,
            "reasoning_only": True,
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _recovery_candidates_from(
        self,
        rollback_candidates: list[dict[str, Any]],
        failed_execution_recovery: dict[str, Any],
        replay_safety: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = []
        if replay_safety.get("safe"):
            candidates.extend(copy.deepcopy(rollback_candidates))
        failed_candidates = failed_execution_recovery.get("candidates")
        if isinstance(failed_candidates, list):
            candidates.extend(copy.deepcopy(failed_candidates))
        return sorted(
            candidates,
            key=lambda item: (
                self._safe_text(item.get("candidate_type")),
                self._safe_text(item.get("candidate_id")),
            ),
        )

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list[Any]:
        return copy.deepcopy(value) if isinstance(value, list) else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def reason_runtime_recovery(source: Any) -> RuntimeRecoveryReasoningReport:
    return RuntimeRecoveryReasoner().reason(source)


__all__ = [
    "RuntimeRecoveryReasoner",
    "RuntimeRecoveryReasoningReport",
    "reason_runtime_recovery",
]
