from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MutationSandboxPaths:
    root: Path
    runs: Path
    patches: Path
    snapshots: Path
    reports: Path
    rollback: Path


@dataclass(frozen=True)
class MutationSandboxRun:
    run_id: str
    created_at: str
    workspace_root: str
    sandbox_root: str
    run_dir: str
    snapshot_dir: str
    patch_dir: str
    report_dir: str
    rollback_dir: str


class MutationSandbox:
    """
    Controlled Mutation Sandbox.

    This layer isolates self-edit / repair / mutation work from the main workspace.
    It does not execute mutations by itself. It only creates reproducible,
    auditable filesystem boundaries for later mutation execution.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        sandbox_root: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox_root = (
            Path(sandbox_root).resolve()
            if sandbox_root is not None
            else self.workspace_root / "workspace" / "mutation_sandbox"
        )

        self.paths = MutationSandboxPaths(
            root=self.sandbox_root,
            runs=self.sandbox_root / "runs",
            patches=self.sandbox_root / "patches",
            snapshots=self.sandbox_root / "snapshots",
            reports=self.sandbox_root / "reports",
            rollback=self.sandbox_root / "rollback",
        )

    def ensure_layout(self) -> MutationSandboxPaths:
        for path in asdict(self.paths).values():
            Path(path).mkdir(parents=True, exist_ok=True)
        return self.paths

    def create_run(self, label: str | None = None) -> MutationSandboxRun:
        self.ensure_layout()

        timestamp = _utc_timestamp()
        safe_label = _safe_label(label)
        run_id = f"{timestamp}-{safe_label}-{uuid.uuid4().hex[:8]}" if safe_label else f"{timestamp}-{uuid.uuid4().hex[:8]}"

        run_dir = self.paths.runs / run_id
        snapshot_dir = self.paths.snapshots / run_id
        patch_dir = self.paths.patches / run_id
        report_dir = self.paths.reports / run_id
        rollback_dir = self.paths.rollback / run_id

        for path in (run_dir, snapshot_dir, patch_dir, report_dir, rollback_dir):
            path.mkdir(parents=True, exist_ok=False)

        run = MutationSandboxRun(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            workspace_root=str(self.workspace_root),
            sandbox_root=str(self.sandbox_root),
            run_dir=str(run_dir),
            snapshot_dir=str(snapshot_dir),
            patch_dir=str(patch_dir),
            report_dir=str(report_dir),
            rollback_dir=str(rollback_dir),
        )

        self.write_run_manifest(run)
        return run

    def write_run_manifest(self, run: MutationSandboxRun) -> Path:
        manifest_path = Path(run.run_dir) / "manifest.json"
        manifest_path.write_text(
            json.dumps(asdict(run), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def write_report(
        self,
        run: MutationSandboxRun,
        name: str,
        payload: dict[str, Any],
    ) -> Path:
        report_name = _safe_filename(name, default="report")
        if not report_name.endswith(".json"):
            report_name = f"{report_name}.json"

        report_path = Path(run.report_dir) / report_name
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report_path

    def snapshot_paths(
        self,
        run: MutationSandboxRun,
        relative_paths: list[str],
    ) -> list[Path]:
        """
        Copy selected workspace paths into this run's snapshot directory.

        This is intentionally path-list based. The sandbox must not silently copy
        the whole repo because later mutation review needs explicit scope.
        """
        copied: list[Path] = []
        snapshot_root = Path(run.snapshot_dir)

        for relative_path in relative_paths:
            source = (self.workspace_root / relative_path).resolve()
            _assert_inside(self.workspace_root, source)

            if not source.exists():
                raise FileNotFoundError(f"Snapshot source does not exist: {relative_path}")

            destination = snapshot_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)

            if source.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)

            copied.append(destination)

        self.write_report(
            run,
            "snapshot_report",
            {
                "run_id": run.run_id,
                "snapshot_count": len(copied),
                "snapshots": [str(path) for path in copied],
            },
        )

        return copied

    def rollback_paths(
        self,
        run: MutationSandboxRun,
        relative_paths: list[str],
    ) -> list[Path]:
        """
        Copy selected workspace paths into rollback storage before mainline apply.
        """
        copied: list[Path] = []
        rollback_root = Path(run.rollback_dir)

        for relative_path in relative_paths:
            source = (self.workspace_root / relative_path).resolve()
            _assert_inside(self.workspace_root, source)

            if not source.exists():
                raise FileNotFoundError(f"Rollback source does not exist: {relative_path}")

            destination = rollback_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)

            if source.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)

            copied.append(destination)

        self.write_report(
            run,
            "rollback_report",
            {
                "run_id": run.run_id,
                "rollback_count": len(copied),
                "rollback_items": [str(path) for path in copied],
            },
        )

        return copied


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_label(label: str | None) -> str:
    if not label:
        return ""

    cleaned = []
    for char in label.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in ("-", "_", ".", " "):
            cleaned.append("-")

    value = "".join(cleaned).strip("-")
    while "--" in value:
        value = value.replace("--", "-")

    return value[:64]


def _safe_filename(name: str, default: str) -> str:
    value = _safe_label(name)
    return value or default


def _assert_inside(root: Path, target: Path) -> None:
    root_resolved = root.resolve()
    target_resolved = target.resolve()

    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace root: {target}") from exc