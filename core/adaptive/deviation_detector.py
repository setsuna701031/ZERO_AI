from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.adaptive.adaptive_contract import DeviationReport


class DeviationDetector:
    """Compare one executed step with its explicit runtime expectations."""

    CONTRACT_MARKERS = ("contract_violation", "contract violation", "invalid contract")
    TRANSIENT_MARKERS = ("timeout", "timed out", "transient", "temporarily unavailable", "rate limit")

    def detect(
        self,
        *,
        task_id: str,
        step: Mapping[str, Any],
        step_result: Mapping[str, Any],
        evidence_refs: Sequence[str] = (),
    ) -> DeviationReport:
        step_id = str(step.get("id") or step.get("step_id") or "")
        observed = copy.deepcopy(dict(step_result))
        expected = copy.deepcopy(step.get("expected", {"ok": True}))
        error_text = self._error_text(step_result).lower()

        if self._is_contract_violation(step_result, error_text):
            return self._report(task_id, step_id, expected, observed, "contract_violation", "critical", False, evidence_refs)

        missing = self._missing_artifacts(step, step_result)
        if missing:
            observed["missing_artifacts"] = missing
            return self._report(task_id, step_id, expected, observed, "artifact_missing", "high", True, evidence_refs)

        if not bool(step_result.get("ok", False)):
            reason = "transient_error" if any(marker in error_text for marker in self.TRANSIENT_MARKERS) else "step_failed"
            return self._report(task_id, step_id, expected, observed, reason, "high", True, evidence_refs)

        if isinstance(expected, Mapping):
            expected_ok = expected.get("ok")
            if expected_ok is not None and bool(expected_ok) != bool(step_result.get("ok")):
                return self._report(task_id, step_id, expected, observed, "observation_mismatch", "medium", True, evidence_refs)

        return self._report(task_id, step_id, expected, observed, "no_deviation", "none", True, evidence_refs, detected=False)

    def _missing_artifacts(self, step: Mapping[str, Any], result: Mapping[str, Any]) -> list[str]:
        expected = step.get("expected_artifacts")
        if not isinstance(expected, list):
            expected_mapping = step.get("expected")
            expected = expected_mapping.get("artifacts") if isinstance(expected_mapping, Mapping) else []
        expected_names = [str(item) for item in expected or [] if str(item).strip()]
        if not expected_names:
            return []

        observed: set[str] = set()
        for source in (result, result.get("result")):
            if not isinstance(source, Mapping):
                continue
            artifacts = source.get("artifacts") or source.get("artifact_paths")
            if isinstance(artifacts, Mapping):
                observed.update(str(value) for value in artifacts.values())
                observed.update(str(key) for key in artifacts)
            elif isinstance(artifacts, list):
                for item in artifacts:
                    if isinstance(item, Mapping):
                        observed.update(str(item.get(key)) for key in ("id", "artifact_id", "name", "path") if item.get(key))
                    else:
                        observed.add(str(item))

        missing: list[str] = []
        for name in expected_names:
            if name in observed or Path(name).exists():
                continue
            missing.append(name)
        return missing

    def _is_contract_violation(self, result: Mapping[str, Any], error_text: str) -> bool:
        if bool(result.get("contract_violation")):
            return True
        error = result.get("error")
        error_type = str(error.get("type") if isinstance(error, Mapping) else "").lower()
        return any(marker in error_text or marker in error_type for marker in self.CONTRACT_MARKERS)

    @staticmethod
    def _error_text(result: Mapping[str, Any]) -> str:
        error = result.get("error")
        if isinstance(error, Mapping):
            return " ".join(str(error.get(key) or "") for key in ("type", "message", "reason"))
        return str(error or result.get("message") or "")

    @staticmethod
    def _report(
        task_id: str,
        step_id: str,
        expected: Any,
        observed: Any,
        reason: str,
        severity: str,
        recoverable: bool,
        evidence_refs: Sequence[str],
        *,
        detected: bool = True,
    ) -> DeviationReport:
        return DeviationReport(
            task_id=task_id,
            step_id=step_id,
            expected=expected,
            observed=observed,
            deviation_detected=detected,
            reason=reason,
            severity=severity,
            recoverable=recoverable,
            evidence_refs=tuple(str(ref) for ref in evidence_refs),
        )


__all__ = ["DeviationDetector"]
