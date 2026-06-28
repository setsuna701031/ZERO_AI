from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from core.planning.planner import Planner
from core.tasks.planner_gateway_runtime import run_scheduler_planner_gateway


def _should_force_deterministic_task_planner(self, goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False

    shared_markers = [
        "workspace/shared/",
        "shared/",
        "workspace\\shared\\",
        "shared\\",
    ]
    verify_markers = [
        " verify ",
        " verifies ",
        " verified ",
        " verify",
        "verifies the file exists",
        "verify the file exists",
        "check that",
        "confirm that",
        "contains",
        "equals",
        "exists",
        "????",
        "check",
        "????",
    ]

    if any(marker in text for marker in shared_markers):
        return True
    return any(marker in text for marker in verify_markers)


def _plan_goal_via_forced_deterministic_planner(self, goal: str) -> Optional[Dict[str, Any]]:
    context = {
        "user_input": goal,
        "workspace": self.workspace_dir,
    }
    route = {
        "mode": "task",
        "task": True,
    }

    planners: List[Any] = []

    agent_loop = getattr(self, "agent_loop", None)
    deterministic_planner = getattr(agent_loop, "planner", None) if agent_loop is not None else None
    if deterministic_planner is not None:
        planners.append(deterministic_planner)

    try:
        planners.append(
            Planner(
                workspace_dir=self.workspace_dir,
                workspace_root=self.workspace_dir,
                debug=bool(getattr(self, "debug", False)),
            )
        )
    except Exception:
        pass

    seen = set()
    unique_planners: List[Any] = []
    for planner in planners:
        if planner is None:
            continue
        pid = id(planner)
        if pid in seen:
            continue
        seen.add(pid)
        unique_planners.append(planner)

    for planner in unique_planners:
        plan = None
        plan_fn = getattr(planner, "plan", None)
        if callable(plan_fn):
            try:
                plan = plan_fn(context=context, user_input=goal, route=route)
            except TypeError:
                try:
                    plan = plan_fn(user_input=goal, context=context, route=route)
                except TypeError:
                    try:
                        plan = plan_fn(goal)
                    except Exception:
                        plan = None
            except Exception:
                plan = None

        if plan is None:
            plan = self._call_planner_like(planner, context=context, user_input=goal, route=route)

        normalized = self._normalize_external_plan(plan)
        if isinstance(normalized, dict):
            steps = normalized.get("steps", [])
            if isinstance(steps, list) and steps:
                return normalized

    return None


def _plan_goal_via_agent_planners(
    self,
    goal: str,
    document_payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    agent_loop = getattr(self, "agent_loop", None)
    if agent_loop is None:
        return None

    planners: List[Any] = []
    llm_planner = getattr(agent_loop, "llm_planner", None)
    deterministic_planner = getattr(agent_loop, "planner", None)

    if llm_planner is not None:
        planners.append(llm_planner)
    if deterministic_planner is not None:
        planners.append(deterministic_planner)

    context = {
        "user_input": goal,
        "workspace": self.workspace_dir,
    }
    route = {
        "mode": "task",
        "task": True,
    }

    if isinstance(document_payload, dict) and document_payload:
        context.update(copy.deepcopy(document_payload))
        route["document_task"] = True

    for planner in planners:
        plan = self._call_planner_like(planner, context=context, user_input=goal, route=route)
        normalized = self._normalize_external_plan(plan)
        if normalized is not None:
            return normalized

    return None


def _call_planner_like(
    self,
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Dict[str, Any],
) -> Any:
    if planner is None:
        return None

    request = {
        "context": context,
        "user_input": user_input,
        "route": route,
        "goal": user_input,
    }

    def _contract_payload_to_external_plan(payload: Any) -> Optional[Dict[str, Any]]:
        """Convert a valid planner contract payload into legacy external-plan shape.

        Phase10-G-9 keeps the scheduler compatibility boundary intact:
        gateway/contract output gets first chance only when it can be
        represented as the existing external planner shape.  Otherwise the
        raw legacy planner result is returned unchanged.
        """
        if not isinstance(payload, dict):
            return None

        if payload.get("is_valid") is False:
            return None

        action = str(payload.get("action") or "").strip().lower()
        if action in {"", "noop", "repair", "rollback"}:
            return None

        target_path = payload.get("target_path")
        target_path_text = str(target_path or "").strip()
        content_text = str(payload.get("content") or "")
        command_text = str(payload.get("command") or "").strip()
        goal_text = str(payload.get("goal") or user_input or "").strip()
        reason_text = str(payload.get("reason") or "").strip()

        step: Dict[str, Any]
        intent = action

        if action == "read_file":
            if not target_path_text:
                return None
            step = {
                "type": "read_file",
                "path": target_path_text,
                "target_path": target_path_text,
            }
        elif action == "write_file":
            if not target_path_text:
                return None
            step = {
                "type": "write_file",
                "path": target_path_text,
                "target_path": target_path_text,
                "content": content_text,
            }
        elif action == "append_file":
            if not target_path_text:
                return None
            step = {
                "type": "append_file",
                "path": target_path_text,
                "target_path": target_path_text,
                "content": content_text,
            }
        elif action == "verify_file":
            if not target_path_text:
                return None
            step = {
                "type": "verify",
                "path": target_path_text,
                "target_path": target_path_text,
            }
            if reason_text:
                step["reason"] = reason_text
        elif action == "run_command":
            if not command_text:
                return None
            step = {
                "type": "command",
                "command": command_text,
            }
        else:
            return None

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        step["planner_contract_action"] = action
        if metadata:
            step["metadata"] = copy.deepcopy(metadata)

        return {
            "planner_mode": "planner_contract_gateway",
            "intent": intent,
            "final_answer": goal_text or f"planned via planner contract: {action}",
            "steps": [step],
            "planner_contract": {
                "contract_version": str(payload.get("contract_version") or ""),
                "action": action,
                "raw_action": str(payload.get("raw_action") or ""),
                "is_valid": bool(payload.get("is_valid", True)),
                "contract_errors": copy.deepcopy(payload.get("contract_errors") or []),
                "contract_warnings": copy.deepcopy(payload.get("contract_warnings") or []),
                "adapter_ok": payload.get("adapter_ok"),
                "runtime_entry_ok": payload.get("runtime_entry_ok"),
                "planner_gateway_ok": payload.get("planner_gateway_ok"),
                "scheduler_planner_gateway_used": payload.get("scheduler_planner_gateway_used"),
                "scheduler_planner_legacy_fallback_used": payload.get("scheduler_planner_legacy_fallback_used"),
            },
        }

    def _gateway_first_or_legacy(raw_plan: Any) -> Any:
        try:
            gateway_result = run_scheduler_planner_gateway(
                lambda _request, _raw_plan=raw_plan: _raw_plan,
                request,
                legacy_payload=raw_plan if isinstance(raw_plan, dict) else None,
                allow_legacy_fallback=True,
            )
        except Exception:
            return raw_plan

        gateway_plan = _contract_payload_to_external_plan(getattr(gateway_result, "payload", None))
        if isinstance(gateway_plan, dict):
            return gateway_plan

        # Compatibility rule: legacy external plans keep their original shape
        # until the downstream scheduler normalizer is fully migrated.
        return raw_plan

    for method_name in ("plan", "run", "__call__"):
        method = getattr(planner, method_name, None)
        if not callable(method):
            continue

        candidate_calls = [
            {"context": context, "user_input": user_input, "route": route},
            {"context": context, "user_input": user_input},
            {"context": context},
            {"user_input": user_input, "route": route},
            {"user_input": user_input},
        ]

        for kwargs in candidate_calls:
            try:
                raw_plan = method(**kwargs)
                return _gateway_first_or_legacy(raw_plan)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            raw_plan = method(user_input)
            return _gateway_first_or_legacy(raw_plan)
        except Exception:
            return None

    return None


def _normalize_external_plan(self, plan: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(plan, dict):
        return None

    def _contract_payload_to_external_plan(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        if payload.get("is_valid") is False:
            return None

        if payload.get("scheduler_planner_runtime_ok") is False:
            return None

        action = str(payload.get("action") or "").strip().lower()
        if action in {"", "noop", "repair", "rollback"}:
            return None

        target_path = payload.get("target_path")
        target_path_text = str(target_path or "").strip()
        content_text = str(payload.get("content") or "")
        command_text = str(payload.get("command") or "").strip()
        goal_text = str(payload.get("goal") or "").strip()
        reason_text = str(payload.get("reason") or "").strip()

        step: Dict[str, Any]
        intent = action

        if action == "read_file":
            if not target_path_text:
                return None
            step = {
                "type": "read_file",
                "path": target_path_text,
                "target_path": target_path_text,
            }
        elif action == "write_file":
            if not target_path_text:
                return None
            step = {
                "type": "write_file",
                "path": target_path_text,
                "target_path": target_path_text,
                "content": content_text,
            }
        elif action == "append_file":
            if not target_path_text:
                return None
            step = {
                "type": "append_file",
                "path": target_path_text,
                "target_path": target_path_text,
                "content": content_text,
            }
        elif action == "verify_file":
            if not target_path_text:
                return None
            step = {
                "type": "verify",
                "path": target_path_text,
                "target_path": target_path_text,
            }
            if reason_text:
                step["reason"] = reason_text
        elif action == "run_command":
            if not command_text:
                return None
            step = {
                "type": "command",
                "command": command_text,
            }
        else:
            return None

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        step["planner_contract_action"] = action
        if metadata:
            step["metadata"] = copy.deepcopy(metadata)

        return {
            "planner_mode": "planner_contract_gateway",
            "intent": intent,
            "final_answer": goal_text or f"planned via planner contract: {action}",
            "steps": [step],
            "planner_contract": {
                "contract_version": str(payload.get("contract_version") or ""),
                "action": action,
                "raw_action": str(payload.get("raw_action") or ""),
                "is_valid": bool(payload.get("is_valid", True)),
                "contract_errors": copy.deepcopy(payload.get("contract_errors") or []),
                "contract_warnings": copy.deepcopy(payload.get("contract_warnings") or []),
                "adapter_ok": payload.get("adapter_ok"),
                "runtime_entry_ok": payload.get("runtime_entry_ok"),
                "planner_gateway_ok": payload.get("planner_gateway_ok"),
                "scheduler_planner_gateway_used": payload.get("scheduler_planner_gateway_used"),
                "scheduler_planner_legacy_fallback_used": payload.get("scheduler_planner_legacy_fallback_used"),
            },
        }

    contract_plan = _contract_payload_to_external_plan(plan)
    if isinstance(contract_plan, dict):
        return contract_plan

    steps = []
    if isinstance(plan.get("steps"), list):
        steps = copy.deepcopy(plan.get("steps", []))
    elif isinstance(plan.get("plan"), dict) and isinstance(plan["plan"].get("steps"), list):
        steps = copy.deepcopy(plan["plan"].get("steps", []))

    if not isinstance(steps, list) or not steps:
        return None

    normalized_steps: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type") or "").strip()
        if not step_type:
            continue
        normalized_steps.append(copy.deepcopy(step))

    if not normalized_steps:
        return None

    return {
        "planner_mode": str(plan.get("planner_mode") or "external_task_planner"),
        "intent": str(plan.get("intent") or normalized_steps[0].get("type") or "task"),
        "final_answer": str(plan.get("final_answer") or f"planned {len(normalized_steps)} steps"),
        "steps": normalized_steps,
        "meta": copy.deepcopy(plan.get("meta", {})) if isinstance(plan.get("meta"), dict) else {},
    }
