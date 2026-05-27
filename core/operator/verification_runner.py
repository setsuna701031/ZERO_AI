from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


@dataclass(frozen=True)
class OperatorVerificationResult:
    verification_id: str
    command: str
    ok: bool
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    authority_required: bool = True
    authority_valid: bool = False
    execution_surface: str = "operator_verification"
    evidence_refs: tuple[str, ...] = ()
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = list(self.evidence_refs)
        return payload


def run_verification_command(
    command: str,
    *,
    authority: Mapping[str, Any] | None = None,
    task: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    executor: Any = None,
) -> OperatorVerificationResult:
    from core.runtime.execution_authority import validate_authority_metadata
    from core.runtime.step_executor import StepExecutor

    validation = validate_authority_metadata(authority or {}, surface="operator_verification")
    if not validation.get("ok"):
        return _result(command, ok=False, returncode=1, stderr=str(validation.get("reason") or "operator_verification_requires_authority"), authority_valid=False)
    runner = executor or StepExecutor(workspace_root=str((context or {}).get("repo_root") or "."))
    raw = runner.execute_step(
        {"type": "operator_verification", "command": str(command or ""), "surface": "operator_verification"},
        task=dict(task or {}),
        context={**dict(context or {}), "authority": dict(authority or {})},
    )
    payload = raw.get("result") if isinstance(raw, Mapping) and isinstance(raw.get("result"), Mapping) else raw if isinstance(raw, Mapping) else {}
    ok = bool(raw.get("ok")) if isinstance(raw, Mapping) else bool(payload.get("ok"))
    return _result(
        command,
        ok=ok,
        returncode=int(payload.get("returncode") or (0 if ok else 1)),
        stdout=str(payload.get("stdout") or raw.get("message") if isinstance(raw, Mapping) else ""),
        stderr=str(payload.get("stderr") or ""),
        authority_valid=True,
        evidence_refs=(raw.get("canonical_evidence") or {}).get("evidence_refs") if isinstance(raw, Mapping) and isinstance(raw.get("canonical_evidence"), Mapping) else (),
    )


def run_verification_suite(
    commands: Any,
    *,
    authority: Mapping[str, Any] | None = None,
    task: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    executor: Any = None,
) -> tuple[OperatorVerificationResult, ...]:
    return tuple(
        run_verification_command(command, authority=authority, task=task, context=context, executor=executor)
        for command in _text_tuple(commands)
    )


def normalize_verification_result(result: OperatorVerificationResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = result.to_dict() if isinstance(result, OperatorVerificationResult) else copy.deepcopy(dict(result))
    return _normalize_value(payload)


def _result(
    command: str,
    *,
    ok: bool,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    authority_valid: bool,
    evidence_refs: Any = None,
) -> OperatorVerificationResult:
    base = {
        "command": str(command or ""),
        "ok": bool(ok),
        "returncode": int(returncode),
        "stdout": str(stdout or ""),
        "stderr": str(stderr or ""),
        "authority_required": True,
        "authority_valid": bool(authority_valid),
        "execution_surface": "operator_verification",
        "evidence_refs": list(_text_tuple(evidence_refs)),
    }
    digest = _digest(base)
    return OperatorVerificationResult(
        verification_id="operator_verification:" + digest[:16],
        command=base["command"],
        ok=base["ok"],
        returncode=base["returncode"],
        stdout=base["stdout"],
        stderr=base["stderr"],
        authority_valid=base["authority_valid"],
        evidence_refs=tuple(base["evidence_refs"]),
        normalized_digest=digest,
    )


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
