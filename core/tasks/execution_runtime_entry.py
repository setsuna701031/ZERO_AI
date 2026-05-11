from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.tasks.execution_contract_adapter import adapt_execution_step


@dataclass(frozen=True)
class ExecutionRuntimeEntryResult:
    ok: bool
    step: Dict[str, Any]
    result: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    invoked: bool = False
    invocation_error: Optional[str] = None


def run_execution_runtime_entry(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
) -> ExecutionRuntimeEntryResult:
    adapted = adapt_execution_step(raw_step)
    step = dict(adapted.step)
    step["execution_runtime_entry_step_ok"] = adapted.ok

    if not adapted.ok:
        step["execution_runtime_entry_invoked"] = False
        step["execution_runtime_entry_ok"] = False
        step["execution_runtime_entry_error"] = ";".join(adapted.errors) or "invalid_execution_step"

        return ExecutionRuntimeEntryResult(
            ok=False,
            step=step,
            result={
                "ok": False,
                "action": "execution_step_rejected",
                "error": step["execution_runtime_entry_error"],
                "step": step,
            },
            errors=list(adapted.errors),
            warnings=list(adapted.warnings),
            invoked=False,
            invocation_error=step["execution_runtime_entry_error"],
        )

    try:
        raw_result = _invoke_executor(executor, step, method_name=method_name)
    except Exception as exc:
        error = f"execution_invocation_failed:{type(exc).__name__}:{exc}"
        step["execution_runtime_entry_invoked"] = False
        step["execution_runtime_entry_ok"] = False
        step["execution_runtime_entry_error"] = error

        return ExecutionRuntimeEntryResult(
            ok=False,
            step=step,
            result={
                "ok": False,
                "action": "execution_invocation_failed",
                "error": error,
                "step": step,
            },
            errors=[error],
            warnings=list(adapted.warnings),
            invoked=False,
            invocation_error=error,
        )

    result = _normalize_executor_result(raw_result)
    result.setdefault("step", step)
    result.setdefault("action", str(step.get("type") or "noop"))

    result_ok = bool(result.get("ok", False))
    step["execution_runtime_entry_invoked"] = True
    step["execution_runtime_entry_ok"] = result_ok
    step["execution_runtime_entry_error"] = None if result_ok else str(result.get("error") or "")

    return ExecutionRuntimeEntryResult(
        ok=result_ok,
        step=step,
        result=result,
        errors=[] if result_ok else [str(result.get("error") or "execution_result_not_ok")],
        warnings=list(adapted.warnings),
        invoked=True,
        invocation_error=None,
    )


def export_execution_runtime_result(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
) -> Dict[str, Any]:
    return run_execution_runtime_entry(
        executor,
        raw_step,
        method_name=method_name,
    ).result


def _invoke_executor(executor: Any, step: Dict[str, Any], *, method_name: str) -> Any:
    if callable(executor):
        return executor(step)

    if executor is None:
        raise TypeError("executor is None")

    method = getattr(executor, method_name, None)
    if not callable(method):
        raise AttributeError(f"executor method not callable: {method_name}")

    return method(step)


def _normalize_executor_result(raw_result: Any) -> Dict[str, Any]:
    if isinstance(raw_result, dict):
        result = dict(raw_result)
        result.setdefault("ok", bool(result.get("ok", False)))
        return result

    if raw_result is None:
        return {
            "ok": True,
            "action": "noop",
            "result": None,
        }

    return {
        "ok": bool(raw_result),
        "action": "executor_result",
        "result": raw_result,
    }