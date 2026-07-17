from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping


class RuntimeSurfaceKind(str, Enum):
    EXECUTION = "execution"
    FILE_MUTATION = "file_mutation"
    GIT_MUTATION = "git_mutation"
    RUNTIME_MUTATION = "runtime_mutation"
    READ_ONLY = "read_only"
    REVIEW_POLICY = "review_policy"
    UNKNOWN = "unknown"


class RuntimeSurfaceRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RuntimeSurface:
    name: str
    kind: RuntimeSurfaceKind
    risk: RuntimeSurfaceRisk
    requires_authority: bool
    side_effect: bool
    mutation: bool = False
    read_only: bool = False
    anonymous: bool = False
    requires_transaction: bool = False


_SURFACES: tuple[RuntimeSurface, ...] = (
    RuntimeSurface("command", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("shell", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("run_shell", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("subprocess", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("python_exec", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("run_python", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("tool_execute", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("tool", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("bash", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("powershell", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("cmd", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("write_file", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.MODERATE, True, True, mutation=True),
    RuntimeSurface("append_file", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.MODERATE, True, True, mutation=True),
    RuntimeSurface("delete_file", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("rename_file", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("apply_patch", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("apply-patch", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("apply_unified_diff", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("atomic_edit", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("patch_transaction", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("workspace_write", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.MODERATE, True, True, mutation=True),
    RuntimeSurface("workspace_append", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.MODERATE, True, True, mutation=True),
    RuntimeSurface("repo_edit", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("repo_apply", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("git_commit", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("git_push", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.CRITICAL, True, True, mutation=True),
    RuntimeSurface("git_branch", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("git_checkout", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("git_merge", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("github_write", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.CRITICAL, True, True, mutation=True),
    RuntimeSurface("create_pr", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.CRITICAL, True, True, mutation=True),
    RuntimeSurface("create_issue", RuntimeSurfaceKind.GIT_MUTATION, RuntimeSurfaceRisk.CRITICAL, True, True, mutation=True),
    RuntimeSurface("governed_repair", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("governed_repair_mutation", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("mutation_apply", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("mutation_commit", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("repair_chain_apply", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("recovery_apply", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("rollback_restore", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("code_chain_repair", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("autonomous_code_repair", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("replay_execute", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("replay_mutation", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("replay_repair", RuntimeSurfaceKind.RUNTIME_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("operator_apply_edit", RuntimeSurfaceKind.FILE_MUTATION, RuntimeSurfaceRisk.HIGH, True, True, mutation=True),
    RuntimeSurface("operator_verification", RuntimeSurfaceKind.EXECUTION, RuntimeSurfaceRisk.HIGH, True, True),
    RuntimeSurface("read_file", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("list_files", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("scan_repo", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("operator_repo_scan", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("operator_edit_plan", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("operator_commit_message", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("replay_read", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("replay_verify", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("recovery_read", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("recovery_inspect", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("audit_read", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("evidence_read", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("summarize", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("workspace_read", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("verify", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("verify_file", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("verify_python_syntax", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("python_syntax_check", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("verify_unified_diff", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("verify_patch", RuntimeSurfaceKind.READ_ONLY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("plan", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("review", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("policy_check", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("respond", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("final_answer", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("llm", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
    RuntimeSurface("llm_generate", RuntimeSurfaceKind.REVIEW_POLICY, RuntimeSurfaceRisk.NONE, False, False, read_only=True),
)

_SURFACE_BY_NAME = {surface.name: surface for surface in _SURFACES}
_MUTATION_TOKENS = (
    "write",
    "append",
    "delete",
    "rename",
    "patch",
    "edit",
    "mutation",
    "commit",
    "push",
    "checkout",
    "merge",
    "repair",
    "recovery",
    "rollback",
    "restore",
    "create_pr",
    "create_issue",
)
_EXECUTION_TOKENS = ("command", "shell", "subprocess", "exec", "execute", "run_")


def _normalize_surface_name(surface: Any) -> str:
    if isinstance(surface, Mapping):
        surface = surface.get("surface") or surface.get("type") or surface.get("action") or surface.get("name")
    return str(surface or "").strip().lower().replace(" ", "_")


def list_runtime_surfaces() -> tuple[RuntimeSurface, ...]:
    return tuple(
        replace(surface, requires_transaction=bool(surface.mutation))
        for surface in _SURFACES
    )


def classify_runtime_surface(surface: Any) -> RuntimeSurface:
    name = _normalize_surface_name(surface)
    known = _SURFACE_BY_NAME.get(name)
    if known is not None:
        return replace(known, requires_transaction=bool(known.mutation))
    if name and any(token in name for token in _MUTATION_TOKENS):
        return RuntimeSurface(
            name=name,
            kind=RuntimeSurfaceKind.UNKNOWN,
            risk=RuntimeSurfaceRisk.HIGH,
            requires_authority=True,
            side_effect=True,
            mutation=True,
            anonymous=True,
            requires_transaction=True,
        )
    if name and any(token in name for token in _EXECUTION_TOKENS):
        return RuntimeSurface(
            name=name,
            kind=RuntimeSurfaceKind.UNKNOWN,
            risk=RuntimeSurfaceRisk.HIGH,
            requires_authority=True,
            side_effect=True,
            anonymous=True,
        )
    return RuntimeSurface(
        name=name or "unknown",
        kind=RuntimeSurfaceKind.UNKNOWN,
        risk=RuntimeSurfaceRisk.NONE,
        requires_authority=False,
        side_effect=False,
        read_only=True,
        anonymous=True,
    )


def is_side_effect_surface(surface: Any) -> bool:
    return classify_runtime_surface(surface).side_effect


def assert_surface_requires_authority(surface: Any) -> bool:
    return classify_runtime_surface(surface).requires_authority


def assert_surface_requires_transaction(surface: Any) -> bool:
    return classify_runtime_surface(surface).requires_transaction


def authority_action_type_for_surface(surface: Any) -> str:
    classified = classify_runtime_surface(surface)
    if classified.mutation:
        return "mutation"
    if classified.side_effect:
        return "execute"
    if classified.kind is RuntimeSurfaceKind.REVIEW_POLICY:
        name = classified.name
        if name in {"respond", "final_answer"}:
            return "respond"
        if name in {"llm", "llm_generate", "summarize", "plan", "review", "policy_check"}:
            return "generate" if name in {"llm", "llm_generate"} else "read"
    return "read"
