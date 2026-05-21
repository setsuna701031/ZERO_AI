from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeStagedFilesystem:
    workspace_root: Path
    staging_root: Path
    rollback_root: Path
    transaction_id: str
    staged_paths: tuple[str, ...] = ()

    def stage_from_sandbox(self, sandbox_root: str | Path, relative_path: str) -> "RuntimeStagedFilesystem":
        relative = _normalize_relative_path(relative_path)
        source = (Path(sandbox_root).resolve() / relative).resolve()
        _assert_inside(Path(sandbox_root).resolve(), source)
        target = (self.staging_root.resolve() / relative).resolve()
        _assert_inside(self.staging_root.resolve(), target)
        if not source.exists():
            raise FileNotFoundError(f"runtime_sandbox_source_missing:{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return RuntimeStagedFilesystem(
            workspace_root=self.workspace_root,
            staging_root=self.staging_root,
            rollback_root=self.rollback_root,
            transaction_id=self.transaction_id,
            staged_paths=tuple(sorted(set(self.staged_paths) | {relative})),
        )

    def read_staged_text(self, relative_path: str) -> str:
        relative = _normalize_relative_path(relative_path)
        target = (self.staging_root.resolve() / relative).resolve()
        _assert_inside(self.staging_root.resolve(), target)
        return target.read_text(encoding="utf-8")

    def rollback(self) -> "RuntimeStagedFilesystem":
        clean_root = self.staging_root.parent / f"{self.staging_root.name}.rolled_back"
        clean_root.mkdir(parents=True, exist_ok=True)
        return RuntimeStagedFilesystem(
            workspace_root=self.workspace_root,
            staging_root=clean_root,
            rollback_root=self.rollback_root,
            transaction_id=self.transaction_id,
            staged_paths=(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "staging_root": str(self.staging_root),
            "rollback_root": str(self.rollback_root),
            "transaction_id": self.transaction_id,
            "staged_paths": list(self.staged_paths),
        }


@dataclass(frozen=True)
class RuntimeMutationSandbox:
    filesystem: RuntimeStagedFilesystem

    def stage_paths(self, sandbox_root: str | Path, relative_paths: tuple[str, ...]) -> "RuntimeMutationSandbox":
        fs = self.filesystem
        for relative_path in relative_paths:
            fs = fs.stage_from_sandbox(sandbox_root, relative_path)
        return RuntimeMutationSandbox(fs)

    def to_dict(self) -> dict[str, Any]:
        return {"filesystem": self.filesystem.to_dict(), "mutation_isolated": True}


@dataclass(frozen=True)
class RuntimeVerificationSandbox:
    filesystem: RuntimeStagedFilesystem

    def verification_root(self) -> Path:
        return self.filesystem.staging_root

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_root": str(self.verification_root()),
            "uses_staged_runtime_state": True,
            "transaction_id": self.filesystem.transaction_id,
        }


@dataclass(frozen=True)
class RuntimeIsolationBoundary:
    workspace_root: Path
    sandbox_root: Path
    rollback_root: Path
    staging_root: Path
    transaction_id: str
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("workspace_root", "sandbox_root", "rollback_root", "staging_root"):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)).resolve())
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def mutation_sandbox(self) -> RuntimeMutationSandbox:
        return RuntimeMutationSandbox(
            RuntimeStagedFilesystem(
                workspace_root=self.workspace_root,
                staging_root=self.staging_root,
                rollback_root=self.rollback_root,
                transaction_id=self.transaction_id,
            )
        )

    def verification_sandbox(self, filesystem: RuntimeStagedFilesystem) -> RuntimeVerificationSandbox:
        if filesystem.transaction_id != self.transaction_id:
            raise ValueError("runtime_verification_sandbox_transaction_mismatch")
        return RuntimeVerificationSandbox(filesystem)

    def validate_paths(self, relative_paths: tuple[str, ...]) -> bool:
        for path in relative_paths:
            relative = _normalize_relative_path(path)
            if self.denied_paths and any(_path_in_scope(relative, denied) for denied in self.denied_paths):
                raise ValueError(f"runtime_isolation_denied_path:{relative}")
            if self.allowed_paths and not any(_path_in_scope(relative, allowed) for allowed in self.allowed_paths):
                raise ValueError(f"runtime_isolation_path_outside_scope:{relative}")
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "sandbox_root": str(self.sandbox_root),
            "rollback_root": str(self.rollback_root),
            "staging_root": str(self.staging_root),
            "transaction_id": self.transaction_id,
            "allowed_paths": list(self.allowed_paths),
            "denied_paths": list(self.denied_paths),
            "metadata": dict(self.metadata),
        }


def write_isolation_manifest(boundary: RuntimeIsolationBoundary, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(boundary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return target


def _normalize_relative_path(path: str) -> str:
    relative = str(path or "").replace("\\", "/").strip().lstrip("/")
    if not relative or ".." in Path(relative).parts:
        raise ValueError(f"runtime_invalid_relative_path:{path}")
    return relative


def _path_in_scope(path: str, scope: str) -> bool:
    clean_scope = _normalize_relative_path(scope).rstrip("/")
    return path == clean_scope or path.startswith(clean_scope + "/")


def _assert_inside(root: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"runtime_isolation_path_escapes_root:{target}") from exc


__all__ = [
    "RuntimeIsolationBoundary",
    "RuntimeMutationSandbox",
    "RuntimeStagedFilesystem",
    "RuntimeVerificationSandbox",
    "write_isolation_manifest",
]
