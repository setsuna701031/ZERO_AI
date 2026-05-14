from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runtime.mutation_patch_apply import (
    apply_patch_plan,
    create_patch_plan,
    read_patch_plan,
    write_patch_plan,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)


def _session() :
    return create_mutation_session(
        intent="Apply sandbox mutation",
        initiator="test",
        reason="Verify controlled patch apply",
        scope=MutationScope(
            allowed_paths=("core/runtime", "tests"),
            denied_paths=("core/runtime/secrets",),
            max_files_changed=3,
            allow_new_files=True,
        ),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.REVIEW_REQUIRED,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
    )


def test_create_patch_plan_rejects_out_of_scope_path() -> None:
    session = _session()

    with pytest.raises(ValueError):
        create_patch_plan(
            session=session,
            relative_paths=["README.md"],
        )


def test_create_patch_plan_rejects_too_many_files() -> None:
    session = _session()

    with pytest.raises(ValueError):
        create_patch_plan(
            session=session,
            relative_paths=[
                "core/runtime/a.py",
                "core/runtime/b.py",
                "core/runtime/c.py",
                "core/runtime/d.py",
            ],
        )


def test_write_and_read_patch_plan(tmp_path: Path) -> None:
    session = _session()
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/a.py"],
    )

    path = write_patch_plan(plan, tmp_path)
    loaded = read_patch_plan(path)

    assert loaded.session_id == plan.session_id
    assert loaded.sandbox_run_id == plan.sandbox_run_id
    assert loaded.items[0].relative_path == "core/runtime/a.py"


def test_apply_patch_plan_replaces_file_and_creates_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session()
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = apply_patch_plan(
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        session=session,
        plan=plan,
    )

    assert result.applied is True
    assert result.applied_paths == ("core/runtime/demo.py",)
    assert result.rollback_paths == ("core/runtime/demo.py",)

    assert target.read_text(encoding="utf-8") == "VERSION = 2\n"

    rollback_file = rollback / "core" / "runtime" / "demo.py"
    assert rollback_file.exists()
    assert rollback_file.read_text(encoding="utf-8") == "VERSION = 1\n"

    assert result.report_path is not None
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["session_id"] == session.session_id
    assert report["applied_paths"] == ["core/runtime/demo.py"]


def test_apply_patch_plan_can_create_new_file_when_allowed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "new_file.py"
    source.parent.mkdir(parents=True)
    source.write_text("NEW_FILE = True\n", encoding="utf-8")

    session = _session()
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/new_file.py"],
    )

    result = apply_patch_plan(
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        session=session,
        plan=plan,
    )

    assert result.applied is True
    assert result.applied_paths == ("core/runtime/new_file.py",)
    assert result.rollback_paths == ()

    target = workspace / "core" / "runtime" / "new_file.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "NEW_FILE = True\n"


def test_apply_patch_plan_rejects_new_file_when_disallowed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    source = sandbox / "core" / "runtime" / "new_file.py"
    source.parent.mkdir(parents=True)
    source.write_text("NEW_FILE = True\n", encoding="utf-8")

    session = create_mutation_session(
        intent="Apply sandbox mutation",
        initiator="test",
        reason="Verify new file rejection",
        scope=MutationScope(
            allowed_paths=("core/runtime",),
            allow_new_files=False,
        ),
        sandbox_run_id="sandbox-run-1",
    )
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/new_file.py"],
    )

    with pytest.raises(ValueError):
        apply_patch_plan(
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            session=session,
            plan=plan,
        )


def test_apply_patch_plan_dry_run_does_not_modify_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    session = _session()
    plan = create_patch_plan(
        session=session,
        relative_paths=["core/runtime/demo.py"],
    )

    result = apply_patch_plan(
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        session=session,
        plan=plan,
        dry_run=True,
    )

    assert result.applied is False
    assert result.applied_paths == ("core/runtime/demo.py",)
    assert result.rollback_paths == ()
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"


def test_apply_patch_plan_rejects_session_mismatch(tmp_path: Path) -> None:
    session_a = _session()
    session_b = create_mutation_session(
        intent="Other session",
        initiator="test",
        reason="Mismatch",
        scope=MutationScope(allowed_paths=("core/runtime",)),
    )

    plan = create_patch_plan(
        session=session_a,
        relative_paths=["core/runtime/demo.py"],
    )

    with pytest.raises(ValueError):
        apply_patch_plan(
            workspace_root=tmp_path / "workspace",
            sandbox_source_root=tmp_path / "sandbox",
            rollback_root=tmp_path / "rollback",
            report_root=tmp_path / "reports",
            session=session_b,
            plan=plan,
        )