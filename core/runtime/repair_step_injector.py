from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

try:
    from core.runtime.runtime_mode import READONLY_RUNTIME_MODES, RuntimeMode
except Exception:  # pragma: no cover - compatibility fallback
    class RuntimeMode(str):
        EXECUTE = "execute"
        REPLAY = "replay"
        AUDIT = "audit"
        REPAIR_REPLAY = "repair_replay"

    READONLY_RUNTIME_MODES = {"replay", "audit", "repair_replay"}


@dataclass
class InjectedRepairStep:
    id: str
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    source: str = "repair_step_injector_v1"

    def to_step(self) -> Dict[str, Any]:
        step = {
            "id": self.id,
            "type": self.type,
        }
        step.update(copy.deepcopy(self.payload))
        step["repair_injected"] = True
        step["repair_source"] = self.source
        if self.reason:
            step["repair_reason"] = self.reason
        return step

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["step"] = self.to_step()
        return data


@dataclass
class RepairInjectionResult:
    ok: bool
    reason: str = ""
    injected_steps: List[InjectedRepairStep] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_steps(self) -> List[Dict[str, Any]]:
        return [item.to_step() for item in self.injected_steps]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "injected_steps": [item.to_dict() for item in self.injected_steps],
            "steps": self.to_steps(),
            "diagnostics": copy.deepcopy(self.diagnostics),
        }


class RepairStepInjector:
    def build_injection(
        self,
        *,
        repair_plan: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        failed_step: Optional[Dict[str, Any]] = None,
        failed_result: Optional[Dict[str, Any]] = None,
        verify_command: str = "",
        report_path: str = "AER_AUTO_REPAIR_REPORT.md",
    ) -> RepairInjectionResult:
        runtime_mode = self._runtime_mode_from_payload(repair_plan, task, failed_step, failed_result)
        if self._is_readonly_runtime_mode(runtime_mode):
            return RepairInjectionResult(
                ok=False,
                reason=f"{runtime_mode} runtime cannot inject repair steps",
                diagnostics={
                    "runtime_mode": runtime_mode,
                    "guard_mode": "readonly_runtime_repair_injection_blocked",
                },
            )

        if not isinstance(repair_plan, dict):
            return RepairInjectionResult(
                ok=False,
                reason="repair_plan must be a dict",
                diagnostics={"repair_plan_type": type(repair_plan).__name__},
            )

        if not bool(repair_plan.get("ok", False)):
            return RepairInjectionResult(
                ok=False,
                reason="repair_plan is not ok",
                diagnostics={"repair_plan": copy.deepcopy(repair_plan)},
            )

        actions = repair_plan.get("actions")
        if not isinstance(actions, list) or not actions:
            return RepairInjectionResult(
                ok=False,
                reason="repair_plan has no actions",
                diagnostics={"repair_plan": copy.deepcopy(repair_plan)},
            )

        task_id = self._task_id(task)
        base_id = self._safe_id(task_id or "repair")
        injected: List[InjectedRepairStep] = []

        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                continue

            action_type = str(action.get("type") or "").strip().lower()
            if action_type != "write_file":
                continue

            path = str(action.get("path") or "").strip()
            content = str(action.get("content") or "")

            if not path:
                continue

            injected.append(
                InjectedRepairStep(
                    id=f"{base_id}_repair_governed_mutation_{index}",
                    type="governed_repair_mutation",
                    payload={
                        "task_id": task_id or "repair_task",
                        "proposal_id": f"{base_id}_proposal_{index}",
                        "goal": str(
                            action.get("reason")
                            or repair_plan.get("summary")
                            or "governed runtime repair mutation"
                        ),
                        "mutation": {
                            "op_type": "write_file",
                            "target_path": path,
                            "content": content,
                        },
                        "allowed_roots": [
                            path.replace("\\", "/").split("/", 1)[0]
                            if "/" in path.replace("\\", "/")
                            else "."
                        ],
                        "scope": str(action.get("scope") or "sandbox"),
                        "repair_injected": True,
                    },
                    reason=str(action.get("reason") or "governed repair mutation"),
                )
            )

            command = str(verify_command or "").strip()
            if not command and path.lower().endswith(".py"):
                command = f"python -m py_compile {path}"

            if command:
                injected.append(
                    InjectedRepairStep(
                        id=f"{base_id}_repair_verify_candidate_{index}",
                        type="run_python",
                        payload={
                            "command": command,
                            "command_cwd": self._resolve_command_cwd(task=task, failed_step=failed_step),
                        },
                        reason="verify repaired candidate",
                    )
                )

        if not injected:
            return RepairInjectionResult(
                ok=False,
                reason="repair_plan actions could not be converted into runtime steps",
                diagnostics={"repair_plan": copy.deepcopy(repair_plan)},
            )

        summary = str(repair_plan.get("summary") or "").strip()
        classification = str(repair_plan.get("classification") or "").strip()
        confidence = repair_plan.get("confidence", "")

        report_content = self._build_report_content(
            repair_plan=repair_plan,
            failed_step=failed_step,
            failed_result=failed_result,
            injected_steps=[step.to_step() for step in injected],
        )

        injected.append(
            InjectedRepairStep(
                id=f"{base_id}_repair_write_report",
                type="write_file",
                payload={
                    "path": report_path,
                    "content": report_content,
                    "scope": "sandbox",
                },
                reason="write auto repair report",
            )
        )

        injected.append(
            InjectedRepairStep(
                id=f"{base_id}_repair_verify_report",
                type="verify_file",
                payload={
                    "path": report_path,
                    "contains": "AER_AUTO_REPAIR_PLAN_OK",
                },
                reason="verify auto repair report",
            )
        )

        return RepairInjectionResult(
            ok=True,
            reason="repair steps generated",
            injected_steps=injected,
            diagnostics={
                "task_id": task_id,
                "classification": classification,
                "summary": summary,
                "confidence": confidence,
                "action_count": len(actions),
                "injected_step_count": len(injected),
                "governed_repair_mutation_enabled": True,
            },
        )

    def inject_steps_into_state(
        self,
        *,
        runtime_state: Dict[str, Any],
        injected_steps: List[Dict[str, Any]],
        insert_after_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not isinstance(runtime_state, dict):
            raise TypeError("runtime_state must be a dict")

        runtime_mode = self._runtime_mode_from_payload(runtime_state)
        if self._is_readonly_runtime_mode(runtime_mode):
            raise PermissionError(f"{runtime_mode} runtime cannot inject repair steps into state")

        if not isinstance(injected_steps, list):
            raise TypeError("injected_steps must be a list")

        state = copy.deepcopy(runtime_state)
        steps = state.get("steps")
        if not isinstance(steps, list):
            steps = []
            state["steps"] = steps

        if insert_after_index is None:
            current = self._safe_int(state.get("current_step_index"), 0)
            insert_at = max(0, min(len(steps), current + 1))
        else:
            insert_at = max(0, min(len(steps), int(insert_after_index) + 1))

        normalized_steps = [copy.deepcopy(step) for step in injected_steps if isinstance(step, dict)]
        state["steps"] = steps[:insert_at] + normalized_steps + steps[insert_at:]
        state["steps_total"] = len(state["steps"])

        repair_context = state.setdefault("repair_context", {})
        if isinstance(repair_context, dict):
            injections = repair_context.setdefault("injections", [])
            if isinstance(injections, list):
                injections.append(
                    {
                        "insert_at": insert_at,
                        "injected_step_count": len(normalized_steps),
                        "injected_step_ids": [
                            str(step.get("id") or "")
                            for step in normalized_steps
                            if isinstance(step, dict)
                        ],
                    }
                )
            repair_context["last_injection_version"] = "repair_step_injector_v1"

        return state

    def _build_report_content(
        self,
        *,
        repair_plan: Dict[str, Any],
        failed_step: Optional[Dict[str, Any]],
        failed_result: Optional[Dict[str, Any]],
        injected_steps: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "classification": repair_plan.get("classification"),
            "summary": repair_plan.get("summary"),
            "reason": repair_plan.get("reason"),
            "confidence": repair_plan.get("confidence"),
            "failed_step": copy.deepcopy(failed_step or {}),
            "failed_result_summary": self._compact_failure(failed_result),
            "injected_steps": copy.deepcopy(injected_steps),
        }

        return (
            "AER_AUTO_REPAIR_PLAN_OK\n\n"
            "ZERO generated a repair plan and converted it into governed runtime repair steps.\n\n"
            "```json\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n```\n"
        )

    def _compact_failure(self, failed_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(failed_result, dict):
            return {}

        error = failed_result.get("error")
        result = failed_result.get("result")

        compact = {
            "ok": failed_result.get("ok"),
            "step_type": failed_result.get("step_type"),
            "message": failed_result.get("message"),
            "final_answer": failed_result.get("final_answer"),
            "error": copy.deepcopy(error) if isinstance(error, dict) else error,
        }

        if isinstance(result, dict):
            nested = result.get("result")
            if isinstance(nested, dict):
                compact["stdout"] = str(nested.get("stdout") or "")[-2000:]
                compact["stderr"] = str(nested.get("stderr") or "")[-2000:]
                compact["returncode"] = nested.get("returncode")
                compact["cwd"] = nested.get("cwd")
                compact["command"] = nested.get("command")
            else:
                compact["stdout"] = str(result.get("stdout") or "")[-2000:]
                compact["stderr"] = str(result.get("stderr") or "")[-2000:]
                compact["returncode"] = result.get("returncode")
                compact["cwd"] = result.get("cwd")
                compact["command"] = result.get("command")

        return compact

    def _resolve_command_cwd(
        self,
        *,
        task: Optional[Dict[str, Any]],
        failed_step: Optional[Dict[str, Any]],
    ) -> str:
        if isinstance(failed_step, dict):
            for key in ("command_cwd", "cwd_override", "cwd"):
                value = failed_step.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        if isinstance(task, dict):
            for key in ("sandbox_dir", "task_dir", "target_repo_root"):
                value = task.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _task_id(self, task: Optional[Dict[str, Any]]) -> str:
        if not isinstance(task, dict):
            return ""
        return str(
            task.get("task_id")
            or task.get("id")
            or task.get("task_name")
            or ""
        ).strip()

    def _runtime_mode_from_payload(self, *payloads: Any) -> str:
        for payload in payloads:
            if not isinstance(payload, dict):
                continue

            value = str(payload.get("runtime_mode") or "").strip().lower()
            if value:
                return value

            runtime_context = payload.get("runtime_context")
            if isinstance(runtime_context, dict):
                value = str(runtime_context.get("runtime_mode") or "").strip().lower()
                if value:
                    return value

            repair_context = payload.get("repair_context")
            if isinstance(repair_context, dict):
                value = str(repair_context.get("runtime_mode") or "").strip().lower()
                if value:
                    return value

        return str(getattr(RuntimeMode, "EXECUTE", "execute")).strip().lower()

    def _is_readonly_runtime_mode(self, mode: Any) -> bool:
        text = str(mode or "").strip().lower()
        readonly_values = {
            str(item.value if hasattr(item, "value") else item).strip().lower()
            for item in READONLY_RUNTIME_MODES
        }
        return text in readonly_values

    def _safe_id(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return "repair"
        safe = []
        for ch in text:
            if ch.isalnum() or ch in {"_", "-"}:
                safe.append(ch)
            else:
                safe.append("_")
        return "".join(safe) or "repair"

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)


def build_repair_injection(
    *,
    repair_plan: Dict[str, Any],
    task: Optional[Dict[str, Any]] = None,
    failed_step: Optional[Dict[str, Any]] = None,
    failed_result: Optional[Dict[str, Any]] = None,
    verify_command: str = "",
    report_path: str = "AER_AUTO_REPAIR_REPORT.md",
) -> Dict[str, Any]:
    return RepairStepInjector().build_injection(
        repair_plan=repair_plan,
        task=task,
        failed_step=failed_step,
        failed_result=failed_result,
        verify_command=verify_command,
        report_path=report_path,
    ).to_dict()