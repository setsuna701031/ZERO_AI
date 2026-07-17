from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


@dataclass(frozen=True)
class OperatorEditAction:
    action_id: str
    action_type: str
    target_file: str
    description: str = ""
    requires_authority: bool = True
    requires_transaction: bool = True
    prediction_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prediction_refs"] = list(self.prediction_refs)
        return payload


@dataclass(frozen=True)
class OperatorEditPlan:
    plan_id: str
    task_id: str
    user_intent: str
    impacted_files: tuple[str, ...]
    target_files: tuple[str, ...]
    actions: tuple[OperatorEditAction, ...]
    test_commands: tuple[str, ...]
    risk_level: str = "moderate"
    evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    authoritative: bool = False
    mutation_executed: bool = False
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["actions"] = [item.to_dict() for item in self.actions]
        for key in ("impacted_files", "target_files", "test_commands", "evidence_refs", "memory_refs", "prediction_refs"):
            payload[key] = list(getattr(self, key))
        return payload


def create_operator_edit_plan(
    *,
    task_id: str,
    user_intent: str,
    impacted_files: Any,
    target_files: Any = None,
    test_commands: Any = None,
    risk_level: str = "moderate",
    evidence_refs: Any = None,
    memory_refs: Any = None,
    prediction_refs: Any = None,
) -> OperatorEditPlan:
    impacted = _text_tuple(impacted_files)
    targets = _text_tuple(target_files) or impacted
    tests = _text_tuple(test_commands) or ("python -m pytest tests -q",)
    predictions = _append_unique(prediction_refs, _prediction_refs_for_plan(task_id, user_intent, targets))
    actions = tuple(
        OperatorEditAction(
            action_id=_stable_id("operator_edit_action", task_id, target, index, user_intent),
            action_type="controlled_edit",
            target_file=target,
            description=f"Plan controlled edit for {target}",
            prediction_refs=predictions,
        )
        for index, target in enumerate(targets)
    )
    base = {
        "task_id": str(task_id or ""),
        "user_intent": str(user_intent or ""),
        "impacted_files": list(impacted),
        "target_files": list(targets),
        "actions": [action.to_dict() for action in actions],
        "test_commands": list(tests),
        "risk_level": str(risk_level or "moderate"),
        "evidence_refs": list(_text_tuple(evidence_refs)),
        "memory_refs": list(_text_tuple(memory_refs)),
        "prediction_refs": list(predictions),
        "authoritative": False,
        "mutation_executed": False,
    }
    digest = _digest(base)
    plan = OperatorEditPlan(
        plan_id="operator_edit_plan:" + digest[:16],
        task_id=base["task_id"],
        user_intent=base["user_intent"],
        impacted_files=tuple(base["impacted_files"]),
        target_files=tuple(base["target_files"]),
        actions=actions,
        test_commands=tuple(base["test_commands"]),
        risk_level=base["risk_level"],
        evidence_refs=tuple(base["evidence_refs"]),
        memory_refs=tuple(base["memory_refs"]),
        prediction_refs=tuple(base["prediction_refs"]),
        normalized_digest=digest,
    )
    validate_operator_edit_plan(plan)
    return plan


def validate_operator_edit_plan(plan: OperatorEditPlan | Mapping[str, Any]) -> bool:
    payload = normalize_operator_edit_plan(plan)
    if payload.get("authoritative") or payload.get("authority_granted"):
        raise AssertionError("edit plan is not execution authority")
    if payload.get("mutation_executed") or payload.get("file_written") or payload.get("transaction_created"):
        raise AssertionError("edit plan cannot write files")
    for key in ("impacted_files", "target_files", "test_commands", "risk_level"):
        if not payload.get(key):
            raise AssertionError(f"edit plan missing {key}")
    assert_edit_plan_requires_authority_for_mutation(payload)
    assert_edit_plan_preserves_scope(payload)
    return True


def normalize_operator_edit_plan(plan: OperatorEditPlan | Mapping[str, Any]) -> dict[str, Any]:
    payload = plan.to_dict() if isinstance(plan, OperatorEditPlan) else copy.deepcopy(dict(plan))
    return _normalize_value(payload)


def assert_edit_plan_requires_authority_for_mutation(plan: OperatorEditPlan | Mapping[str, Any]) -> bool:
    payload = normalize_operator_edit_plan(plan)
    for action in payload.get("actions") or []:
        if action.get("action_type") in {"controlled_edit", "write", "patch", "apply"}:
            if not action.get("requires_authority") or not action.get("requires_transaction"):
                raise AssertionError("operator mutation plan requires authority and transaction")
    return True


def assert_edit_plan_preserves_scope(plan: OperatorEditPlan | Mapping[str, Any]) -> bool:
    payload = normalize_operator_edit_plan(plan)
    impacted = set(payload.get("impacted_files") or [])
    targets = set(payload.get("target_files") or [])
    if not targets.issubset(impacted):
        raise AssertionError("edit plan target files must be within impacted files")
    return True


def _prediction_refs_for_plan(task_id: str, user_intent: str, target_files: tuple[str, ...]) -> tuple[str, ...]:
    try:
        from core.runtime.runtime_prediction_engine import predict_mutation_impact

        prediction = predict_mutation_impact(
            {
                "task_id": task_id,
                "step_id": "operator_edit_plan",
                "trace_id": f"operator-trace:{task_id}",
                "affected_files": target_files,
                "reasoning_summary": user_intent,
            }
        )
        return (prediction.prediction_id,)
    except Exception:
        return ()


def _append_unique(*values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        for item in _text_tuple(value):
            if item not in result:
                result.append(item)
    return tuple(result)


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


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{hashlib.sha256(json.dumps(_normalize_value(parts), sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]}"


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
