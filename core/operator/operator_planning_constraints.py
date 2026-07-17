from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable


def _norm(path: Any) -> str:
    text = str(path or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def _is_under(path: str, root: str) -> bool:
    path = _norm(path)
    root = _norm(root)
    if not root:
        return True
    return path == root or path.startswith(root + "/")


def _looks_like_runtime_impl(path: str) -> bool:
    p = _norm(path)
    return p.startswith("core/runtime/") or p.startswith("core/tasks/") or p.startswith("core/agent/")


def _looks_like_test(path: str) -> bool:
    p = _norm(path)
    return p.startswith("tests/") and p.endswith(".py")


@dataclass(frozen=True)
class PlanningConstraints:
    allow_paths: tuple[str, ...] = ()
    deny_paths: tuple[str, ...] = ()
    max_files: int | None = None
    test_only: bool = False
    implementation_locked: bool = False
    single_file_only: bool = False
    requested_target_file: str | None = None

    @classmethod
    def from_request(
        cls,
        *,
        allow_paths: Iterable[str] | None = None,
        deny_paths: Iterable[str] | None = None,
        user_intent: str = "",
        max_files: int | None = None,
    ) -> "PlanningConstraints":
        intent = user_intent.upper()
        normalized_allow = tuple(_norm(p) for p in (allow_paths or ()) if _norm(p))
        normalized_deny = tuple(_norm(p) for p in (deny_paths or ()) if _norm(p))

        single = "STRICT SINGLE FILE ONLY" in intent or "SINGLE FILE ONLY" in intent
        test_only = "TEST FILE ONLY" in intent or "TESTS/" in intent
        impl_locked = (
            "DO NOT MODIFY RUNTIME IMPLEMENTATION" in intent
            or "DO NOT TOUCH RUNTIME IMPLEMENTATION" in intent
            or "DO NOT INSPECT OR SELECT RUNTIME IMPLEMENTATION" in intent
            or "DO NOT MODIFY CORE/RUNTIME" in intent
        )

        requested = None
        for token in user_intent.replace('"', " ").replace("'", " ").split():
            token = _norm(token.strip(".,:;()[]{}"))
            if token.startswith("tests/") and token.endswith(".py"):
                requested = token
                break

        if single and not requested and len(normalized_allow) == 1:
            only = normalized_allow[0]
            if only.endswith(".py"):
                requested = only

        if single and max_files is None:
            max_files = 1

        return cls(
            allow_paths=normalized_allow,
            deny_paths=normalized_deny,
            max_files=max_files,
            test_only=test_only,
            implementation_locked=impl_locked,
            single_file_only=single,
            requested_target_file=requested,
        )

    def allows(self, path: Any) -> tuple[bool, str | None]:
        p = _norm(path)
        if not p:
            return False, "empty_path"

        if self.single_file_only and self.requested_target_file:
            if p != _norm(self.requested_target_file):
                return False, "single_file_only"

        if self.allow_paths and not any(_is_under(p, root) for root in self.allow_paths):
            return False, "outside_allow_paths"

        if self.deny_paths and any(_is_under(p, root) for root in self.deny_paths):
            return False, "inside_deny_paths"

        if self.test_only and not _looks_like_test(p):
            return False, "test_only"

        if self.implementation_locked and _looks_like_runtime_impl(p):
            return False, "implementation_locked"

        return True, None


@dataclass
class ConstraintResult:
    edit_plan: dict[str, Any]
    selected_files: list[str]
    constraint_status: str
    constraint_violations: list[dict[str, Any]] = field(default_factory=list)
    constraint_filtered_files: list[str] = field(default_factory=list)


def apply_planning_constraints(
    *,
    edit_plan: dict[str, Any] | None,
    selected_files: Iterable[str] | None,
    constraints: PlanningConstraints,
    block_on_violation: bool = False,
) -> ConstraintResult:
    plan = dict(edit_plan or {})
    violations: list[dict[str, Any]] = []
    filtered: list[str] = []

    def keep(path: Any, source: str) -> bool:
        ok, reason = constraints.allows(path)
        if ok:
            return True
        p = _norm(path)
        filtered.append(p)
        violations.append({"path": p, "source": source, "reason": reason})
        return False

    actions = []
    for action in list(plan.get("actions") or []):
        target = action.get("target_file")
        if keep(target, "actions.target_file"):
            actions.append(action)
    plan["actions"] = actions

    for key in ("target_files", "impacted_files"):
        values = []
        for path in list(plan.get(key) or []):
            if keep(path, key):
                values.append(_norm(path))
        plan[key] = values

    selected = []
    for path in list(selected_files or []):
        if keep(path, "selected_files"):
            selected.append(_norm(path))

    if constraints.single_file_only and constraints.requested_target_file:
        wanted = _norm(constraints.requested_target_file)
        if not selected and constraints.allows(wanted)[0]:
            selected = [wanted]
        for key in ("target_files", "impacted_files"):
            if not plan.get(key) and constraints.allows(wanted)[0]:
                plan[key] = [wanted]

    unique_filtered = sorted(set(x for x in filtered if x))
    status = "ok" if not unique_filtered else "constraint_filtered"

    if block_on_violation and unique_filtered:
        status = "constraint_violation"
        plan["actions"] = []
        plan["target_files"] = []
        plan["impacted_files"] = []
        selected = []

    if constraints.max_files is not None:
        selected = selected[: constraints.max_files]
        for key in ("target_files", "impacted_files"):
            plan[key] = list(plan.get(key) or [])[: constraints.max_files]
        plan["actions"] = list(plan.get("actions") or [])[: constraints.max_files]

    plan["constraint_status"] = status
    plan["constraint_violations"] = violations
    plan["constraint_filtered_files"] = unique_filtered

    return ConstraintResult(
        edit_plan=plan,
        selected_files=selected,
        constraint_status=status,
        constraint_violations=violations,
        constraint_filtered_files=unique_filtered,
    )