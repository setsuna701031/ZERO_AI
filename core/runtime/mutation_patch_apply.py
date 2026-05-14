from __future__ import annotations

import filecmp
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from core.runtime.mutation_session import (
    MutationScope,
    MutationSession,
    validate_mutation_file_count,
    validate_mutation_path,
)


@dataclass(frozen=True)
class MutationPatchItem:
    relative_path: str
    operation: str = "replace"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationPatchPlan:
    session_id: str
    sandbox_run_id: str | None
    items: tuple[MutationPatchItem, ...]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sandbox_run_id": self.sandbox_run_id,
            "created_at": self.created_at,
            "items": [item.to_dict() for item in self.items],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class MutationPatchApplyResult:
    session_id: str
    applied: bool
    applied_paths: tuple[str, ...]
    skipped_paths: tuple[str, ...]
    rollback_paths: tuple[str, ...]
    report_path: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_patch_plan(
    *,
    session: MutationSession,
    relative_paths: list[str],
) -> MutationPatchPlan:
    normalized_paths = tuple(_normalize_relative_path(path) for path in relative_paths)

    if not validate_mutation_file_count(list(normalized_paths), session.scope):
        raise ValueError("Mutation patch exceeds max_files_changed scope limit.")

    for path in normalized_paths:
        if not validate_mutation_path(path, session.scope):
            raise ValueError(f"Mutation patch path outside session scope: {path}")

    items = tuple(MutationPatchItem(relative_path=path) for path in normalized_paths)

    return MutationPatchPlan(
        session_id=session.session_id,
        sandbox_run_id=session.sandbox_run_id,
        items=items,
    )


def write_patch_plan(
    plan: MutationPatchPlan,
    directory: str | Path,
    filename: str = "mutation_patch_plan.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_text(plan.to_json(), encoding="utf-8")
    return target_path


def read_patch_plan(path: str | Path) -> MutationPatchPlan:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = tuple(
        MutationPatchItem(
            relative_path=str(item["relative_path"]),
            operation=str(item.get("operation", "replace")),
        )
        for item in data.get("items", [])
    )

    return MutationPatchPlan(
        session_id=str(data["session_id"]),
        sandbox_run_id=data.get("sandbox_run_id"),
        created_at=str(data["created_at"]),
        items=items,
    )


def apply_patch_plan(
    *,
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    session: MutationSession,
    plan: MutationPatchPlan,
    dry_run: bool = False,
) -> MutationPatchApplyResult:
    if plan.session_id != session.session_id:
        raise ValueError("Patch plan session_id does not match mutation session.")

    workspace = Path(workspace_root).resolve()
    sandbox = Path(sandbox_source_root).resolve()
    rollback = Path(rollback_root).resolve()
    reports = Path(report_root).resolve()

    rollback.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    applied_paths: list[str] = []
    skipped_paths: list[str] = []
    rollback_paths: list[str] = []

    for item in plan.items:
        if item.operation != "replace":
            raise ValueError(f"Unsupported patch operation: {item.operation}")

        relative_path = _normalize_relative_path(item.relative_path)

        if not validate_mutation_path(relative_path, session.scope):
            raise ValueError(f"Patch path outside mutation scope: {relative_path}")

        source_path = (sandbox / relative_path).resolve()
        target_path = (workspace / relative_path).resolve()
        rollback_path = (rollback / relative_path).resolve()

        _assert_inside(sandbox, source_path)
        _assert_inside(workspace, target_path)
        _assert_inside(rollback, rollback_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Sandbox patch source does not exist: {relative_path}")

        if source_path.is_dir():
            raise ValueError(f"Directory patch apply is not supported yet: {relative_path}")

        if target_path.exists() and target_path.is_dir():
            raise ValueError(f"Cannot replace directory target with file: {relative_path}")

        if target_path.exists() and filecmp.cmp(source_path, target_path, shallow=False):
            skipped_paths.append(relative_path)
            continue

        if not target_path.exists() and not session.scope.allow_new_files:
            raise ValueError(f"Mutation scope does not allow new files: {relative_path}")

        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            rollback_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists():
                shutil.copy2(target_path, rollback_path)
                rollback_paths.append(relative_path)

            shutil.copy2(source_path, target_path)

        applied_paths.append(relative_path)

    report_payload = {
        "session_id": session.session_id,
        "sandbox_run_id": session.sandbox_run_id,
        "dry_run": dry_run,
        "applied": not dry_run,
        "applied_paths": applied_paths,
        "skipped_paths": skipped_paths,
        "rollback_paths": rollback_paths,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    report_path = reports / "mutation_patch_apply_report.json"
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return MutationPatchApplyResult(
        session_id=session.session_id,
        applied=not dry_run,
        applied_paths=tuple(applied_paths),
        skipped_paths=tuple(skipped_paths),
        rollback_paths=tuple(rollback_paths),
        report_path=str(report_path),
    )


def _normalize_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Patch path must be non-empty text.")

    normalized = path.replace("\\", "/").strip()

    while normalized.startswith("./"):
        normalized = normalized[2:]

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise ValueError(f"Patch path must be relative: {path}")

    if any(part == ".." for part in pure_path.parts):
        raise ValueError(f"Patch path escapes workspace: {path}")

    normalized_text = str(pure_path).rstrip("/")

    if normalized_text in ("", "."):
        raise ValueError("Patch path must be non-empty text.")

    return normalized_text


def _assert_inside(root: Path, target: Path) -> None:
    root_resolved = root.resolve()
    target_resolved = target.resolve()

    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes root: {target}") from exc