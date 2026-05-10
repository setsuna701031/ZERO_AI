from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from core.tasks.execution_contract import normalize_execution_step


@dataclass(frozen=True)
class ExecutionAdapterResult:
    ok: bool
    step: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_type: str = ""


def adapt_execution_step(raw_step: Any) -> ExecutionAdapterResult:
    extracted = _extract_step(raw_step)
    contract_result = normalize_execution_step(extracted)

    step = dict(contract_result.step)
    step["execution_adapter_ok"] = contract_result.ok
    step["execution_adapter_errors"] = list(contract_result.errors)
    step["execution_adapter_warnings"] = list(contract_result.warnings)

    return ExecutionAdapterResult(
        ok=contract_result.ok,
        step=step,
        errors=list(contract_result.errors),
        warnings=list(contract_result.warnings),
        source_type=str(step.get("type") or ""),
    )


def export_runtime_execution_step(raw_step: Any) -> Dict[str, Any]:
    return adapt_execution_step(raw_step).step


def _extract_step(raw_step: Any) -> Any:
    if not isinstance(raw_step, Mapping):
        return raw_step

    if isinstance(raw_step.get("step"), Mapping):
        return raw_step["step"]

    if isinstance(raw_step.get("payload"), Mapping):
        return raw_step["payload"]

    if isinstance(raw_step.get("result"), Mapping):
        result = raw_step["result"]
        if isinstance(result.get("step"), Mapping):
            return result["step"]
        return result

    return raw_step