from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime.execution_authority import ensure_authority_metadata, validate_authority_metadata
from core.runtime.runtime_surface_registry import (
    RuntimeSurfaceRisk,
    assert_surface_requires_authority,
    classify_runtime_surface,
    is_side_effect_surface,
)


MUTATION_SURFACES = {
    "command",
    "shell",
    "run_shell",
    "subprocess",
    "python_exec",
    "tool_execute",
    "write_file",
    "append_file",
    "delete_file",
    "rename_file",
    "apply_patch",
    "apply-patch",
    "apply_unified_diff",
    "atomic_edit",
    "patch_transaction",
    "git_commit",
    "git_push",
    "git_branch",
    "git_checkout",
    "git_merge",
    "github_write",
    "create_pr",
    "create_issue",
    "governed_repair",
    "governed_repair_mutation",
    "mutation_apply",
    "mutation_commit",
    "repair_chain_apply",
    "recovery_apply",
    "rollback_restore",
}

READ_ONLY_SURFACES = {
    "read_file",
    "list_files",
    "scan_repo",
    "replay_read",
    "audit_read",
    "evidence_read",
    "summarize",
    "plan",
    "review",
    "policy_check",
}


def test_all_known_mutation_surfaces_are_side_effect_surfaces() -> None:
    for surface in MUTATION_SURFACES:
        classified = classify_runtime_surface(surface)
        assert classified.side_effect is True, surface
        assert is_side_effect_surface(surface) is True
        assert classified.requires_authority is True
        assert classified.risk is not RuntimeSurfaceRisk.NONE


def test_read_only_and_review_surfaces_are_not_side_effect_surfaces() -> None:
    for surface in READ_ONLY_SURFACES:
        classified = classify_runtime_surface(surface)
        assert classified.side_effect is False, surface
        assert is_side_effect_surface(surface) is False
        assert classified.requires_authority is False
        assert classified.risk is RuntimeSurfaceRisk.NONE


def test_side_effect_surfaces_require_authority() -> None:
    for surface in MUTATION_SURFACES:
        assert assert_surface_requires_authority(surface) is True
        validation = validate_authority_metadata({}, surface=surface)
        assert validation["ok"] is False
        assert validation["reason"] == "missing_authority_metadata"


def test_review_policy_and_governance_context_alone_is_not_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "apply_patch", "target_path": "workspace/shared/review.txt"},
        context={
            "governance_snapshot": {"review": True},
            "constitution": {"review_required_actions": ("apply_patch",)},
            "policy_check": {"allowed": True},
        },
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["error"]["type"] == "execution_authority_denied"
    assert result["authority_decision"]["reason"] == "missing_authority_metadata"


def test_unknown_mutation_like_names_fail_closed() -> None:
    classified = classify_runtime_surface("anonymous_mutation_apply")
    assert classified.anonymous is True
    assert classified.side_effect is True
    assert classified.requires_authority is True
    assert classified.risk is not RuntimeSurfaceRisk.NONE


def test_subprocess_run_is_confined_to_runtime_executor() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (root / "core" / "runtime").rglob("*.py"):
        if "subprocess.run(" not in path.read_text(encoding="utf-8"):
            continue
        rel = path.relative_to(root).as_posix()
        if rel != "core/runtime/executor.py":
            offenders.append(rel)

    assert offenders == []


def test_step_executor_blocks_apply_patch_without_authority_before_review(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "apply_patch", "target_path": "workspace/shared/blocked.txt"},
        context={
            "governance_snapshot": _governance(),
            "constitution": _constitution(),
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert result["authority_decision"]["reason"] == "missing_authority_metadata"


def test_step_executor_allows_read_only_or_review_step_without_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "respond", "message": "read-only review surface"}
    )

    assert result["ok"] is True
    assert result.get("authority_decision", {}).get("authority_required") is False
    assert (result.get("error") or {}).get("type") != "execution_authority_denied"


def test_compatibility_adapter_still_allows_valid_legacy_execution_context() -> None:
    metadata, validation = ensure_authority_metadata(
        {},
        task={"id": "legacy-task", "runtime_identity": {"identity_id": "legacy-runtime"}},
        step={"type": "command", "id": "legacy-step"},
        context={"runtime_session_id": "legacy-session"},
        lineage={"request_id": "legacy-request"},
        authority_source="legacy_compatibility_test",
        action_type="execute",
        surface="command",
    )

    assert validation["ok"] is True
    assert metadata["compatibility_authority_adapter"] is True
    assert metadata["task_id"] == "legacy-task"
    assert metadata["step_id"] == "legacy-step"


def _governance() -> dict[str, Any]:
    return {"governance_id": "surface-freeze-governance"}


def _constitution() -> dict[str, Any]:
    return {
        "constitution_version": "surface-freeze",
        "allowed_actions": ("read_file",),
        "review_required_actions": ("apply_patch",),
        "blocked_actions": (),
    }
