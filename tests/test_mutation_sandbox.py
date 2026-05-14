from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runtime.mutation_sandbox import MutationSandbox


def test_mutation_sandbox_creates_layout(tmp_path: Path) -> None:
    sandbox = MutationSandbox(workspace_root=tmp_path)
    paths = sandbox.ensure_layout()

    assert paths.root.exists()
    assert paths.runs.exists()
    assert paths.patches.exists()
    assert paths.snapshots.exists()
    assert paths.reports.exists()
    assert paths.rollback.exists()


def test_mutation_sandbox_creates_run_manifest(tmp_path: Path) -> None:
    sandbox = MutationSandbox(workspace_root=tmp_path)
    run = sandbox.create_run(label="Controlled Mutation Sandbox")

    manifest_path = Path(run.run_dir) / "manifest.json"
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["run_id"] == run.run_id
    assert data["workspace_root"] == str(tmp_path.resolve())
    assert "controlled-mutation-sandbox" in run.run_id


def test_mutation_sandbox_snapshots_explicit_paths(tmp_path: Path) -> None:
    source_file = tmp_path / "core" / "demo.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("print('hello')\n", encoding="utf-8")

    sandbox = MutationSandbox(workspace_root=tmp_path)
    run = sandbox.create_run(label="snapshot-test")

    copied = sandbox.snapshot_paths(run, ["core/demo.py"])

    assert len(copied) == 1
    copied_file = Path(run.snapshot_dir) / "core" / "demo.py"
    assert copied_file.exists()
    assert copied_file.read_text(encoding="utf-8") == "print('hello')\n"

    report_path = Path(run.report_dir) / "snapshot-report.json"
    assert report_path.exists()


def test_mutation_sandbox_creates_rollback_copy(tmp_path: Path) -> None:
    source_file = tmp_path / "core" / "runtime.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("VERSION = 1\n", encoding="utf-8")

    sandbox = MutationSandbox(workspace_root=tmp_path)
    run = sandbox.create_run(label="rollback-test")

    copied = sandbox.rollback_paths(run, ["core/runtime.py"])

    assert len(copied) == 1
    rollback_file = Path(run.rollback_dir) / "core" / "runtime.py"
    assert rollback_file.exists()
    assert rollback_file.read_text(encoding="utf-8") == "VERSION = 1\n"

    report_path = Path(run.report_dir) / "rollback-report.json"
    assert report_path.exists()


def test_mutation_sandbox_rejects_path_escape(tmp_path: Path) -> None:
    sandbox = MutationSandbox(workspace_root=tmp_path)
    run = sandbox.create_run(label="escape-test")

    with pytest.raises(ValueError):
        sandbox.snapshot_paths(run, ["../outside.py"])