from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.runtime_evidence_surface import list_evidence
from core.runtime.runtime_ownership_evidence import (

    RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA,
    export_runtime_ownership_evidence,
)
from core.runtime.runtime_ownership_policy import CANONICAL_EXECUTION_PATH
from core.runtime.runtime_ownership_scan import (
    scan_default_runtime_ownership_surfaces,
    scan_runtime_ownership_paths,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



def test_ownership_scan_detects_direct_scheduler_execution_write_and_mutation(
    tmp_path: Path,
) -> None:
    bad_scheduler = tmp_path / "core" / "tasks" / "scheduler.py"
    bad_scheduler.parent.mkdir(parents=True)
    bad_scheduler.write_text(
        "import subprocess\n"
        "from pathlib import Path\n"
        "from core.runtime.mutation_runtime_pipeline import run_mutation_runtime_pipeline\n"
        "\n"
        "def execute_bad_step():\n"
        "    subprocess.run(['python', '-V'])\n"
        "    Path('x.txt').write_text('bad')\n"
        "    run_mutation_runtime_pipeline()\n",
        encoding="utf-8",
    )

    report = scan_runtime_ownership_paths(
        [bad_scheduler],
        repo_root=tmp_path,
        owner="scheduler",
        include_write_calls=True,
    )
    violation_types = {
        item["violation_type"]
        for item in report["policy"]["violations"]
    }
    symbols = {item["symbol"] for item in report["policy"]["violations"]}

    assert report["ok"] is False
    assert "direct_execution_bypass" in violation_types
    assert "direct_write_bypass" in violation_types
    assert {"subprocess.run", "write_text", "run_mutation_runtime_pipeline"} <= symbols


def test_current_default_runtime_ownership_surface_has_canonical_execution_path() -> None:
    report = scan_default_runtime_ownership_surfaces(include_write_calls=False)

    assert report["policy"]["canonical_execution_path"] == list(CANONICAL_EXECUTION_PATH)
    assert report["ok"] is True
    assert report["policy"]["violations"] == []
    assert "core/runtime/execution_gateway.py" in report["scanned_files"]
    assert "core/runtime/executor.py" in report["scanned_files"]


def test_runtime_ownership_evidence_exports_and_registers_surface_index(
    tmp_path: Path,
) -> None:
    report = {
        "schema": "runtime_ownership_scan_report.v1",
        "ok": False,
        "policy": {
            "violation_count": 1,
            "violations": [
                {
                    "file_path": "core/tasks/scheduler.py",
                    "line": 10,
                    "owner": "scheduler",
                    "violation_type": "direct_execution_bypass",
                    "symbol": "subprocess.run",
                    "reason": "execution must route through runtime.execution_gateway -> runtime.executor",
                    "evidence": {},
                }
            ],
        },
    }

    export = export_runtime_ownership_evidence(
        repo_root=tmp_path,
        task_id="ownership seal",
        ownership_report=report,
    )

    evidence_path = Path(export["evidence_path"])
    exported_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    indexed = list_evidence("ownership seal", repo_root=tmp_path)

    assert evidence_path == (
        tmp_path
        / "workspace"
        / "evidence"
        / "runtime_ownership"
        / "ownership_seal_runtime_ownership.json"
    )
    assert exported_payload["schema"] == "runtime_ownership_scan_report.v1"
    assert exported_payload["evidence_only"] is True
    assert indexed == [
        {
            "task_id": "ownership seal",
            "evidence_type": "runtime_ownership",
            "path": str(evidence_path),
            "metadata": {
                "artifact_path": str(evidence_path),
                "evidence_path": str(evidence_path),
                "schema": "runtime_ownership_scan_report.v1",
                "ok": False,
                "violation_count": 1,
            },
        }
    ]


def test_runtime_ownership_evidence_defaults_schema_for_plain_reports(
    tmp_path: Path,
) -> None:
    export = export_runtime_ownership_evidence(
        repo_root=tmp_path,
        task_id="ownership-plain",
        ownership_report={"ok": True, "policy": {"violation_count": 0}},
    )

    assert export["schema"] == RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA
    assert export["payload"]["schema"] == RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA
    assert export["metadata"]["violation_count"] == 0


def test_ownership_scan_policy_and_evidence_add_no_execution_path() -> None:
    import core.runtime.runtime_ownership_evidence as ownership_evidence
    import core.runtime.runtime_ownership_policy as ownership_policy
    import core.runtime.runtime_ownership_scan as ownership_scan

    source = "\n".join(
        [
            inspect.getsource(ownership_scan),
            inspect.getsource(ownership_policy),
            inspect.getsource(ownership_evidence),
        ]
    )

    assert "from core.agent import agent_loop" not in source
    assert "from core.tasks import scheduler" not in source
    assert "from core.runtime.step_executor import StepExecutor" not in source
    assert "import subprocess" not in source
    assert "import os" not in source
    assert "run_mutation_runtime_pipeline(" not in source
    assert "run_governed_mutation_runtime(" not in source
    assert "run_recovery(" not in source
    assert "execute_recovery(" not in source
