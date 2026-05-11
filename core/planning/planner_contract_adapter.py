from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.planning.planner_contract import normalize_planner_payload


@dataclass(frozen=True)
class PlannerAdapterResult:
    ok: bool
    payload: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_action: str = ""


def adapt_planner_result(raw_result: Any) -> PlannerAdapterResult:
    extracted = _extract_payload(raw_result)
    contract_result = normalize_planner_payload(extracted)

    payload = dict(contract_result.payload)
    payload["adapter_ok"] = contract_result.ok
    payload["adapter_errors"] = list(contract_result.errors)
    payload["adapter_warnings"] = list(contract_result.warnings)

    return PlannerAdapterResult(
        ok=contract_result.ok,
        payload=payload,
        errors=list(contract_result.errors),
        warnings=list(contract_result.warnings),
        source_action=str(payload.get("raw_action") or payload.get("action") or ""),
    )


def export_runtime_safe_payload(raw_result: Any) -> Dict[str, Any]:
    return adapt_planner_result(raw_result).payload


def _extract_payload(raw_result: Any) -> Any:
    if not isinstance(raw_result, Mapping):
        return raw_result

    if isinstance(raw_result.get("payload"), Mapping):
        return raw_result["payload"]

    if isinstance(raw_result.get("plan"), Mapping):
        return raw_result["plan"]

    if isinstance(raw_result.get("result"), Mapping):
        return raw_result["result"]

    return raw_result