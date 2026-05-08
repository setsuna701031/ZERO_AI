from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


TERMINAL_STATUSES = {
    "finished",
    "failed",
    "cancelled",
    "timeout",
}


class RuntimeStateGuardError(ValueError):
    """Raised when a runtime state mutation violates ownership rules."""


@dataclass(frozen=True)
class RuntimeMutationResult:
    ok: bool
    state: Dict[str, Any]
    owner: str
    section: str
    action: str
    changed: bool
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "state": copy.deepcopy(self.state),
            "owner": self.owner,
            "section": self.section,
            "action": self.action,
            "changed": self.changed,
            "warnings": list(self.warnings),
        }


class RuntimeStateGuard:
    """
    Runtime state write-ownership guard.

    This module does not replace TaskRuntime persistence. It provides a narrow
    enforcement layer for components that need to update owned runtime sections
    without accidentally overwriting unrelated runtime state.

    Core rule:
        TaskRuntime owns persistence and normalization.
        Other components may only update sections they explicitly own.

    This first version is intentionally conservative and side-effect free:
        - it never mutates the input state in place
        - it returns a deep-copied updated state
        - it raises RuntimeStateGuardError for illegal writes
    """

    SECTION_OWNERS: Dict[str, Tuple[str, ...]] = {
        "status": ("task_runtime",),
        "steps": ("task_runtime", "task_runner"),
        "current_step_index": ("task_runtime",),
        "steps_total": ("task_runtime",),
        "results": ("task_runtime",),
        "step_results": ("task_runtime",),
        "execution_log": ("task_runtime",),
        "execution_trace": ("task_runner", "task_runtime"),
        "last_step_result": ("task_runtime",),
        "last_error": ("task_runtime",),
        "last_output": ("task_runtime",),
        "final_answer": ("task_runtime",),
        "final_result": ("task_runtime",),
        "next_action": ("task_runtime", "task_runner"),
        "terminal_reason": ("task_runtime",),
        "blockers": ("task_runtime",),
        "active_blocker_count": ("task_runtime",),
        "requires_review": ("task_runtime",),
        "review_status": ("task_runtime",),
        "review_id": ("task_runtime",),
        "review_payload": ("task_runtime",),
        "waiting_reason": ("task_runtime",),
        "repair_context.strategy": ("repair_runtime", "task_runner"),
        "repair_context.regression_verify": ("task_runner", "repair_runtime"),
        "repair_context.rollback": ("repair_runtime", "task_runner"),
        "repair_context.rollback_result": ("repair_runtime", "task_runner"),
        "repair_context.engineering_goal_state": ("task_runtime",),
        "repair_context.repair_session": ("observation_layer", "task_runner"),
        "repair_context.repo_impact": ("repair_runtime", "task_runner"),
        "repair_context.multi_file_plan": ("repair_runtime", "task_runner"),
        "repair_context.dependency_graph": ("repair_runtime", "task_runner"),
    }

    APPEND_ONLY_SECTIONS = {
        "results",
        "step_results",
        "execution_log",
        "execution_trace",
        "repair_context.strategy.strategy_history",
        "repair_context.repair_session.nodes",
        "repair_context.repair_session.edges",
        "repair_context.repair_session.observations",
        "repair_context.repair_session.decisions",
    }

    TERMINAL_ALLOWED_OWNERS = {
        "task_runtime",
    }

    def __init__(
        self,
        *,
        section_owners: Optional[Dict[str, Iterable[str]]] = None,
        append_only_sections: Optional[Iterable[str]] = None,
    ) -> None:
        owners = copy.deepcopy(self.SECTION_OWNERS)
        if isinstance(section_owners, dict):
            for section, values in section_owners.items():
                owners[str(section)] = tuple(str(item) for item in values)

        self.section_owners: Dict[str, Tuple[str, ...]] = owners
        self.append_only_sections = set(self.APPEND_ONLY_SECTIONS)
        if append_only_sections:
            self.append_only_sections.update(str(item) for item in append_only_sections)

    def assert_owner(self, *, section: str, owner: str) -> None:
        section = self._normalize_section(section)
        owner = self._normalize_owner(owner)

        allowed = self.section_owners.get(section)
        if allowed is None:
            raise RuntimeStateGuardError(f"Unknown runtime section: {section}")

        if owner not in allowed:
            raise RuntimeStateGuardError(
                f"Illegal runtime write: owner={owner!r} cannot write section={section!r}; "
                f"allowed={list(allowed)!r}"
            )

    def update_section(
        self,
        state: Dict[str, Any],
        *,
        section: str,
        owner: str,
        patch: Any,
        action: str = "merge",
        allow_terminal_write: bool = False,
    ) -> RuntimeMutationResult:
        """
        Update a runtime section with ownership checks.

        action:
            - "set": replace the section
            - "merge": dict merge for dict sections; otherwise set
            - "append": append one item or extend list with items
        """
        if not isinstance(state, dict):
            raise RuntimeStateGuardError("Runtime state must be a dict")

        section = self._normalize_section(section)
        owner = self._normalize_owner(owner)
        action = str(action or "merge").strip().lower()

        self.assert_owner(section=section, owner=owner)
        self._assert_terminal_write_allowed(
            state=state,
            owner=owner,
            section=section,
            allow_terminal_write=allow_terminal_write,
        )

        updated = copy.deepcopy(state)
        before = self._get_path(updated, section)

        if action == "set":
            self._assert_append_only_not_replaced(section=section, before=before, patch=patch)
            self._set_path(updated, section, copy.deepcopy(patch))
        elif action == "merge":
            merged = self._merge_values(before, patch)
            self._set_path(updated, section, merged)
        elif action == "append":
            appended = self._append_values(before, patch)
            self._set_path(updated, section, appended)
        else:
            raise RuntimeStateGuardError(f"Unsupported runtime mutation action: {action}")

        after = self._get_path(updated, section)
        changed = before != after
        warnings = self._build_warnings(section=section, owner=owner, before=before, after=after)

        return RuntimeMutationResult(
            ok=True,
            state=updated,
            owner=owner,
            section=section,
            action=action,
            changed=changed,
            warnings=tuple(warnings),
        )

    def validate_state(self, state: Dict[str, Any]) -> List[str]:
        warnings: List[str] = []
        if not isinstance(state, dict):
            return ["runtime_state is not a dict"]

        status = str(state.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            next_action = str(state.get("next_action") or "").strip()
            if next_action == "run_next_tick":
                warnings.append("terminal state should not request run_next_tick")

        steps = state.get("steps")
        steps_total = state.get("steps_total")
        if isinstance(steps, list) and isinstance(steps_total, int) and len(steps) != steps_total:
            warnings.append("steps_total does not match len(steps)")

        current_step_index = state.get("current_step_index")
        if isinstance(current_step_index, int) and isinstance(steps_total, int):
            if current_step_index < 0:
                warnings.append("current_step_index is negative")
            if current_step_index > steps_total:
                warnings.append("current_step_index exceeds steps_total")

        repair_context = state.get("repair_context")
        if repair_context is not None and not isinstance(repair_context, dict):
            warnings.append("repair_context is not a dict")

        blockers = state.get("blockers")
        if blockers is not None and not isinstance(blockers, list):
            warnings.append("blockers is not a list")

        return warnings

    def _assert_terminal_write_allowed(
        self,
        *,
        state: Dict[str, Any],
        owner: str,
        section: str,
        allow_terminal_write: bool,
    ) -> None:
        if allow_terminal_write:
            return

        status = str(state.get("status") or "").strip().lower()
        if status not in TERMINAL_STATUSES:
            return

        if owner in self.TERMINAL_ALLOWED_OWNERS:
            return

        raise RuntimeStateGuardError(
            f"Illegal runtime write: owner={owner!r} cannot write section={section!r} "
            f"after terminal status={status!r}"
        )

    def _assert_append_only_not_replaced(self, *, section: str, before: Any, patch: Any) -> None:
        if section not in self.append_only_sections:
            return
        if before in (None, []):
            return
        raise RuntimeStateGuardError(
            f"Illegal runtime write: section={section!r} is append-only and cannot be replaced"
        )

    def _build_warnings(self, *, section: str, owner: str, before: Any, after: Any) -> List[str]:
        warnings: List[str] = []

        if section in self.append_only_sections:
            before_len = len(before) if isinstance(before, list) else 0
            after_len = len(after) if isinstance(after, list) else 0
            if after_len < before_len:
                warnings.append(f"append-only section shrank: {section}")

        if section == "repair_context" and isinstance(before, dict) and isinstance(after, dict):
            missing = sorted(set(before.keys()) - set(after.keys()))
            if missing:
                warnings.append(f"repair_context keys removed: {missing}")

        return warnings

    def _merge_values(self, before: Any, patch: Any) -> Any:
        if isinstance(before, dict) and isinstance(patch, dict):
            merged = copy.deepcopy(before)
            for key, value in patch.items():
                if isinstance(merged.get(key), dict) and isinstance(value, dict):
                    merged[key] = self._merge_values(merged[key], value)
                else:
                    merged[key] = copy.deepcopy(value)
            return merged

        return copy.deepcopy(patch)

    def _append_values(self, before: Any, patch: Any) -> List[Any]:
        result = copy.deepcopy(before) if isinstance(before, list) else []
        if isinstance(patch, list):
            result.extend(copy.deepcopy(patch))
        else:
            result.append(copy.deepcopy(patch))
        return result

    def _get_path(self, state: Dict[str, Any], section: str) -> Any:
        current: Any = state
        for part in section.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return copy.deepcopy(current)

    def _set_path(self, state: Dict[str, Any], section: str, value: Any) -> None:
        parts = section.split(".")
        current = state
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    def _normalize_section(self, section: str) -> str:
        return str(section or "").strip()

    def _normalize_owner(self, owner: str) -> str:
        return str(owner or "").strip().lower()


_DEFAULT_GUARD = RuntimeStateGuard()


def update_runtime_section(
    state: Dict[str, Any],
    *,
    section: str,
    owner: str,
    patch: Any,
    action: str = "merge",
    allow_terminal_write: bool = False,
) -> Dict[str, Any]:
    """
    Convenience wrapper for guarded runtime state updates.

    Returns updated state dict.
    Raises RuntimeStateGuardError on illegal mutation.
    """
    result = _DEFAULT_GUARD.update_section(
        state,
        section=section,
        owner=owner,
        patch=patch,
        action=action,
        allow_terminal_write=allow_terminal_write,
    )
    return result.state


def validate_runtime_state(state: Dict[str, Any]) -> List[str]:
    return _DEFAULT_GUARD.validate_state(state)
