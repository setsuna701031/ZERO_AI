from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_decision_advisor import RuntimeDecisionAdvisor
from core.runtime.runtime_memory_model import RuntimeActivityMemory
from core.runtime.runtime_planner_advisor_bridge import (
    RuntimePlannerAdvisorBridge,
)
from core.runtime.runtime_natural_task_package_generator import (
    build_runtime_operator_package_from_task,
)


RUNTIME_NATURAL_TASK_INTAKE_SCHEMA = "zero.runtime.natural_task_intake.v1"
RUNTIME_NATURAL_TASK_INTAKE_RECORD_SCHEMA = (
    "zero.runtime.natural_task_intake_record.v1"
)
RUNTIME_OPERATOR_PACKAGE_SCHEMA = "zero.runtime.operator_package.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _safe_filename(value: Any) -> str:
    text = _text(value) or "natural-task"
    return "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in text
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )


def _build_package_result(
    goal: str,
    *,
    target_root: Any = ".",
    authority_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return build_runtime_operator_package_from_task(
            goal,
            target_root=target_root,
            authority_context=authority_context,
        )
    except TypeError:
        try:
            return build_runtime_operator_package_from_task(
                goal,
                target_root,
                authority_context,
            )
        except TypeError:
            try:
                return build_runtime_operator_package_from_task(
                    goal,
                    target_root=target_root,
                )
            except TypeError:
                return build_runtime_operator_package_from_task(goal)


def _extract_runtime_operator_package(
    generation_result: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(generation_result)

    candidate = result.get("runtime_operator_package")
    if isinstance(candidate, Mapping):
        return _mapping(candidate)

    candidate = result.get("package")
    if isinstance(candidate, Mapping):
        candidate_mapping = _mapping(candidate)
        if candidate_mapping.get("schema") == RUNTIME_OPERATOR_PACKAGE_SCHEMA:
            return candidate_mapping

    if result.get("schema") == RUNTIME_OPERATOR_PACKAGE_SCHEMA:
        return result

    return {}


def _normalize_package(
    package: Mapping[str, Any],
    *,
    goal: str,
    intake_id: str,
    mode: str,
    target_root: Any,
    authority_context: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(package)
    normalized["schema"] = RUNTIME_OPERATOR_PACKAGE_SCHEMA
    normalized["package_id"] = _text(
        normalized.get("package_id")
    ) or _stable_id(
        "operator-package",
        intake_id,
        goal,
        mode,
    )
    normalized["task_id"] = _text(
        normalized.get("task_id")
    ) or _stable_id(
        "natural-task",
        intake_id,
        goal,
    )
    normalized["goal"] = _text(normalized.get("goal")) or goal
    normalized["requested_mode"] = (
        _text(normalized.get("requested_mode")) or mode
    )
    normalized["target_root"] = (
        normalized.get("target_root") or target_root
    )
    normalized["authority_context"] = _mapping(
        normalized.get("authority_context")
    ) or dict(authority_context)
    normalized["requested_changes"] = (
        list(normalized.get("requested_changes"))
        if isinstance(normalized.get("requested_changes"), list)
        else []
    )
    normalized["validation_required"] = (
        normalized.get("validation_required") is not False
    )
    normalized["rollback_required"] = (
        normalized.get("rollback_required") is not False
    )
    normalized["natural_task_intake_id"] = intake_id
    normalized["natural_task_goal"] = goal
    return normalized


def _activity_log_path(workspace_root: str | Path) -> Path:
    root = Path(workspace_root)
    if root.name == "operator_intake":
        return root.parent / "operator_activity" / "activity.jsonl"
    return root / "operator_activity" / "activity.jsonl"


def _compact_memory_context(
    decision_context: Mapping[str, Any],
) -> dict[str, Any]:
    context = _mapping(decision_context)
    return {
        "schema": context.get("schema")
        or "zero.runtime.activity_memory_query.v1",
        "memory_status": _text(context.get("memory_status")) or "empty",
        "experience_count": int(context.get("experience_count") or 0),
        "successful_paths": list(context.get("successful_paths") or []),
        "prior_denial_reasons": list(
            context.get("prior_denial_reasons") or []
        ),
        "completed_experiences": list(
            context.get("completed_experiences") or []
        ),
        "failed_experiences": list(
            context.get("failed_experiences") or []
        ),
        "rolled_back_experiences": list(
            context.get("rolled_back_experiences") or []
        ),
        "log_path": _text(context.get("log_path")),
        "read_only": True,
        "decision_authority": False,
    }


def _inject_memory_context(
    package: Mapping[str, Any],
    memory_context: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(package)
    metadata = _mapping(result.get("metadata"))
    metadata["memory_context"] = _mapping(memory_context)
    result["metadata"] = metadata
    return result


def _safe_decision_advice(
    goal: str,
    memory_context: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        return RuntimeDecisionAdvisor().advise(goal, memory_context)
    except Exception as exc:
        return {
            "schema": "zero.runtime.decision_advisor.v1",
            "ok": False,
            "advisor_status": "unavailable",
            "goal": goal,
            "previous_success_available": False,
            "recommended_paths": [],
            "prior_denial_reasons": [],
            "risk_flags": [f"advisor_error:{type(exc).__name__}"],
            "planner_hints": [],
            "read_only": True,
            "decision_authority": False,
            "requested_changes_modified": False,
        }


def _inject_decision_advice(
    package: Mapping[str, Any],
    decision_advice: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(package)
    requested_changes = copy.deepcopy(result.get("requested_changes", []))
    metadata = _mapping(result.get("metadata"))
    metadata["decision_advice"] = _mapping(decision_advice)
    result["metadata"] = metadata
    result["requested_changes"] = requested_changes
    return result


def _safe_planner_advisor_bridge(
    goal: str,
    requested_changes: list[Any],
    decision_advice: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        return RuntimePlannerAdvisorBridge().build(
            goal, requested_changes, decision_advice
        )
    except Exception as exc:
        return {
            "schema": "zero.runtime.planner_advisor_bridge.v1",
            "ok": False,
            "bridge_status": "unavailable",
            "goal": goal,
            "planner_hints": [],
            "preferred_paths": [],
            "avoid_risk_flags": [f"bridge_error:{type(exc).__name__}"],
            "candidate_rankings": [],
            "read_only": True,
            "decision_authority": False,
            "requested_changes_modified": False,
        }


def _inject_planner_advisor_bridge(
    package: Mapping[str, Any],
    planner_advisor_bridge: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(package)
    requested_changes = copy.deepcopy(result.get("requested_changes", []))
    metadata = _mapping(result.get("metadata"))
    metadata["planner_advisor_bridge"] = _mapping(planner_advisor_bridge)
    result["metadata"] = metadata
    result["requested_changes"] = requested_changes
    return result


@dataclass(frozen=True)
class RuntimeNaturalTaskIntake:
    workspace_root: str | Path = "workspace/operator_intake"

    @property
    def root(self) -> Path:
        return Path(self.workspace_root)

    @property
    def activity_log_path(self) -> Path:
        return _activity_log_path(self.workspace_root)

    def _decision_context(self, goal: str) -> dict[str, Any]:
        try:
            context = RuntimeActivityMemory(
                self.activity_log_path
            ).decision_context(goal)
        except Exception as exc:
            return {
                "schema": "zero.runtime.activity_memory_query.v1",
                "ok": False,
                "memory_status": "unavailable",
                "goal": goal,
                "completed_experiences": [],
                "failed_experiences": [],
                "rolled_back_experiences": [],
                "successful_paths": [],
                "prior_denial_reasons": [],
                "experience_count": 0,
                "log_path": str(self.activity_log_path),
                "denial_reason": f"activity_memory_read_failed:{type(exc).__name__}",
            }
        return context

    def accept(
        self,
        goal: Any,
        *,
        mode: str = "controlled",
        target_root: Any = ".",
        authority_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        natural_goal = _text(goal)
        requested_mode = _text(mode) or "controlled"
        authority = _mapping(authority_context) or {
            "operator": "RuntimeNaturalTaskIntake",
            "approval_required": True,
            "validation_required": True,
            "rollback_required": True,
            "governed_mutation_adapter_required": (
                requested_mode == "controlled"
            ),
        }

        intake_id = _stable_id(
            "natural-task-intake",
            natural_goal,
            requested_mode,
            target_root,
        )
        created_at = _utc_now()
        safe_id = _safe_filename(intake_id)
        intake_path = self.root / f"intake_{safe_id}.json"
        package_path = self.root / f"package_{safe_id}.json"

        decision_context = self._decision_context(natural_goal)
        memory_context = _compact_memory_context(decision_context)
        decision_advice = _safe_decision_advice(
            natural_goal,
            memory_context,
        )

        generation_result = _build_package_result(
            natural_goal,
            target_root=target_root,
            authority_context=authority,
        )
        generated_package = _extract_runtime_operator_package(
            generation_result
        )
        package = _normalize_package(
            generated_package,
            goal=natural_goal,
            intake_id=intake_id,
            mode=requested_mode,
            target_root=target_root,
            authority_context=authority,
        )
        package = _inject_memory_context(package, memory_context)
        requested_changes_before_advice = copy.deepcopy(
            package.get("requested_changes", [])
        )
        package = _inject_decision_advice(package, decision_advice)
        if package.get("requested_changes") != requested_changes_before_advice:
            package["requested_changes"] = requested_changes_before_advice
        planner_advisor_bridge = _safe_planner_advisor_bridge(
            natural_goal,
            requested_changes_before_advice,
            decision_advice,
        )
        package = _inject_planner_advisor_bridge(
            package, planner_advisor_bridge
        )
        if package.get("requested_changes") != requested_changes_before_advice:
            package["requested_changes"] = requested_changes_before_advice

        intake_record = {
            "schema": RUNTIME_NATURAL_TASK_INTAKE_RECORD_SCHEMA,
            "intake_id": intake_id,
            "goal": natural_goal,
            "requested_mode": requested_mode,
            "target_root": str(target_root),
            "authority_context": dict(authority),
            "created_at": created_at,
            "package_path": str(package_path),
            "status": "accepted",
            "memory_context": copy.deepcopy(memory_context),
            "decision_advice": copy.deepcopy(decision_advice),
            "planner_advisor_bridge": copy.deepcopy(planner_advisor_bridge),
        }

        _write_json(intake_path, intake_record)
        _write_json(package_path, package)

        return {
            "schema": RUNTIME_NATURAL_TASK_INTAKE_SCHEMA,
            "ok": True,
            "action": "accept_natural_task",
            "intake_id": intake_id,
            "goal": natural_goal,
            "requested_mode": requested_mode,
            "target_root": str(target_root),
            "intake_record": intake_record,
            "package": package,
            "intake_path": str(intake_path),
            "package_path": str(package_path),
            "package_generated": (
                package.get("schema") == RUNTIME_OPERATOR_PACKAGE_SCHEMA
            ),
            "validation_required": (
                package.get("validation_required") is True
            ),
            "rollback_required": (
                package.get("rollback_required") is True
            ),
            "memory_context": memory_context,
            "memory_context_injected": True,
            "memory_context_read_only": True,
            "decision_advice": decision_advice,
            "decision_advice_injected": True,
            "decision_advice_read_only": True,
            "planner_advisor_bridge": planner_advisor_bridge,
            "planner_advisor_bridge_injected": True,
            "planner_advisor_bridge_read_only": True,
        }


__all__ = [
    "RUNTIME_NATURAL_TASK_INTAKE_SCHEMA",
    "RUNTIME_NATURAL_TASK_INTAKE_RECORD_SCHEMA",
    "RuntimeNaturalTaskIntake",
]
