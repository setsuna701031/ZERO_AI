from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_replay_reconstruction import (
    RuntimeEvidenceReplayReconstructor,
    RuntimeEvidenceReplayState,
)


FAILED_STATUSES = {"failed", "error", "exception", "blocked", "denied"}
EXPECTED_LINEAGE_TYPES = ["plan", "snapshot", "replay", "audit", "bundle"]


class RuntimeEvidenceReplayValidationReport:
    SCHEMA = "zero.runtime_evidence.replay_validation.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def ok(self) -> bool:
        return bool(self._payload.get("ok", False))

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def issues(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("issues", []))

    def checks(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._payload.get("checks", {}))

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


class RuntimeEvidenceReplayValidator:
    def __init__(self, reconstructor: RuntimeEvidenceReplayReconstructor | None = None) -> None:
        self.reconstructor = reconstructor if reconstructor is not None else RuntimeEvidenceReplayReconstructor()

    def validate(self, source: Any) -> RuntimeEvidenceReplayValidationReport:
        replay_state = self._replay_state(source)
        replay_payload = replay_state.payload
        checks = {
            "sealed_replay": self.validate_sealed_replay(replay_state),
            "replay_integrity": self.validate_replay_integrity(replay_state),
            "event_ordering": self.validate_event_ordering(replay_state),
            "lineage_consistency": self.validate_lineage_consistency(replay_state),
            "rollback_linkage": self.validate_rollback_linkage(replay_state),
            "failed_execution_consistency": self.validate_failed_execution_consistency(replay_state),
        }
        issues = []
        for check_name, check in checks.items():
            if not bool(check.get("ok", False)):
                for issue in check.get("issues", []):
                    safe_issue = self._safe_mapping(issue)
                    safe_issue.setdefault("check", check_name)
                    issues.append(safe_issue)

        payload = {
            "ok": not issues,
            "schema": RuntimeEvidenceReplayValidationReport.SCHEMA,
            "replay_fingerprint": replay_state.fingerprint,
            "snapshot_fingerprint": self._safe_text(replay_payload.get("snapshot_fingerprint")),
            "checks": checks,
            "issue_count": len(issues),
            "issues": issues,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeEvidenceReplayValidationReport(payload)

    def validate_replay_integrity(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        payload = replay_state.payload
        executions = replay_state.execution_replay()
        counts = self._safe_mapping(payload.get("replay_counts"))
        issues = []

        if self._safe_int(counts.get("executions"), 0) != len(executions):
            issues.append(self._issue("execution_count_mismatch", "replay_counts.executions does not match execution replay length"))
        if not self._safe_text(payload.get("fingerprint")):
            issues.append(self._issue("missing_replay_fingerprint", "replay state fingerprint is missing"))
        if not self._safe_text(payload.get("snapshot_fingerprint")):
            issues.append(self._issue("missing_snapshot_fingerprint", "snapshot fingerprint is missing"))
        if not self._is_zero_based_sequence([item.get("replay_order") for item in executions]):
            issues.append(self._issue("execution_replay_order_invalid", "execution replay order must be zero-based and contiguous"))
        if any(not self._safe_text(item.get("execution_id")) for item in executions if isinstance(item, dict)):
            issues.append(self._issue("execution_id_missing", "execution replay contains empty execution_id"))

        return self._check("replay_integrity", issues)

    def validate_event_ordering(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        events = replay_state.event_replay_order()
        issues = []
        if not self._is_zero_based_sequence([event.get("replay_order") for event in events]):
            issues.append(self._issue("event_replay_order_invalid", "event replay order must be zero-based and contiguous"))
        if any(not self._safe_text(event.get("layer")) for event in events if isinstance(event, dict)):
            issues.append(self._issue("event_layer_missing", "event replay contains empty layer"))
        return self._check("event_ordering", issues)

    def validate_lineage_consistency(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        lineage = replay_state.lineage_replay()
        issues = []
        if not lineage:
            sealed = self._safe_mapping(replay_state.payload.get("sealed_state")).get("sealed")
            if sealed:
                issues.append(self._issue("lineage_missing", "sealed replay must include lineage"))
            return self._check("lineage_consistency", issues)

        if not self._is_zero_based_sequence([item.get("replay_order") for item in lineage]):
            issues.append(self._issue("lineage_replay_order_invalid", "lineage replay order must be zero-based and contiguous"))

        lineage_types = [self._safe_text(item.get("lineage_type")) for item in lineage]
        expected_prefix = EXPECTED_LINEAGE_TYPES[: len(lineage_types)]
        if lineage_types != expected_prefix:
            issues.append(
                self._issue(
                    "lineage_type_order_invalid",
                    "lineage type order does not match expected replay chain",
                    expected=expected_prefix,
                    actual=lineage_types,
                )
            )
        if any(not bool(item.get("verified", False)) for item in lineage if item.get("lineage_type") in {"replay", "audit", "bundle"}):
            issues.append(self._issue("lineage_unverified", "replay lineage contains unverified replay/audit/bundle nodes"))
        return self._check("lineage_consistency", issues)

    def validate_rollback_linkage(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        executions = [item.get("execution_id") for item in replay_state.execution_replay()]
        rollback = replay_state.rollback_replay()
        issues = []
        if not rollback.get("found"):
            sealed = self._safe_mapping(replay_state.payload.get("sealed_state")).get("sealed")
            if sealed:
                issues.append(self._issue("rollback_missing", "sealed replay must include rollback linkage"))
            return self._check("rollback_linkage", issues)

        rollback_steps = rollback.get("rollback_steps")
        if not isinstance(rollback_steps, list):
            rollback_steps = []
        rollback_ids = [self._safe_text(item.get("execution_id")) for item in rollback_steps if isinstance(item, dict)]
        expected = list(reversed([self._safe_text(item) for item in executions if self._safe_text(item)]))
        if rollback_ids != expected:
            issues.append(
                self._issue(
                    "rollback_order_mismatch",
                    "rollback order must reverse execution replay order",
                    expected=expected,
                    actual=rollback_ids,
                )
            )
        if not bool(rollback.get("verified", False)):
            issues.append(self._issue("rollback_unverified", "rollback linkage is not verified"))
        return self._check("rollback_linkage", issues)

    def validate_sealed_replay(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        sealed_state = self._safe_mapping(replay_state.payload.get("sealed_state"))
        issues = []
        if not bool(sealed_state.get("sealed", False)):
            issues.append(
                self._issue(
                    "replay_unsealed",
                    "replay state is not sealed",
                    missing_records=self._safe_list(sealed_state.get("missing_records")),
                )
            )
        if not bool(sealed_state.get("complete", False)):
            issues.append(
                self._issue(
                    "replay_incomplete",
                    "replay state is missing evidence records",
                    missing_records=self._safe_list(sealed_state.get("missing_records")),
                )
            )
        return self._check("sealed_replay", issues)

    def validate_failed_execution_consistency(self, source: Any) -> dict[str, Any]:
        replay_state = self._replay_state(source)
        failed = replay_state.failed_execution_replay()
        issues = []
        if not self._is_zero_based_sequence([item.get("replay_order") for item in failed]):
            issues.append(self._issue("failed_replay_order_invalid", "failed execution replay order must be zero-based and contiguous"))
        for item in failed:
            if not isinstance(item, dict):
                continue
            status = self._safe_text(item.get("status")).lower()
            if status not in FAILED_STATUSES:
                issues.append(
                    self._issue(
                        "failed_status_invalid",
                        "failed execution replay contains non-failed status",
                        failed_execution_id=self._safe_text(item.get("failed_execution_id")),
                        status=status,
                    )
                )
            if not self._safe_text(item.get("failed_execution_id")):
                issues.append(self._issue("failed_execution_id_missing", "failed execution id is missing"))
        return self._check("failed_execution_consistency", issues)

    def _replay_state(self, source: Any) -> RuntimeEvidenceReplayState:
        if isinstance(source, RuntimeEvidenceReplayState):
            return RuntimeEvidenceReplayState(source.payload)
        return self.reconstructor.reconstruct(source)

    def _check(self, check_name: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "check": check_name,
            "ok": not issues,
            "issue_count": len(issues),
            "issues": copy.deepcopy(issues),
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return payload

    def _issue(self, issue_type: str, message: str, **metadata: Any) -> dict[str, Any]:
        return {
            "type": issue_type,
            "message": message,
            **copy.deepcopy(metadata),
        }

    def _is_zero_based_sequence(self, values: list[Any]) -> bool:
        try:
            normalized = [int(value) for value in values]
        except Exception:
            return False
        return normalized == list(range(len(normalized)))

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


def validate_runtime_evidence_replay(source: Any) -> RuntimeEvidenceReplayValidationReport:
    return RuntimeEvidenceReplayValidator().validate(source)


__all__ = [
    "RuntimeEvidenceReplayValidationReport",
    "RuntimeEvidenceReplayValidator",
    "validate_runtime_evidence_replay",
]
