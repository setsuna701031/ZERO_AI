from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def test_runtime_workflow_session_contract_imports_when_run_directly(tmp_path: Path) -> None:
    contract_path = Path(__file__).resolve().parent / "test_runtime_workflow_session_contract.py"

    result = subprocess.run(
        [sys.executable, str(contract_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
