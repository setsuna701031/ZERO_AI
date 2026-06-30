from __future__ import annotations

import json

from core.runtime.runtime_engineering_cli import main
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_cli_engineering_command_surface_seal(capsys, tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "core/runtime/runtime_native_engineering_target.py").write_text(
        "VALUE = 'old'\n",
        encoding="utf-8",
    )

    code = main(
        [
            "--workspace",
            str(tmp_path),
            "run",
            "--goal",
            "codex-like cli engineering command",
            "--target-file",
            "core/runtime/runtime_native_engineering_target.py",
            "--content",
            "VALUE = 'new'\n",
            "--verify-contains",
            "new",
            "--keyword",
            "engineering",
            "--keyword",
            "runtime",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["session_id"]
    assert payload["mutation_id"]
    assert (tmp_path / "core/runtime/runtime_native_engineering_target.py").read_text(encoding="utf-8") == "VALUE = 'new'\n"

    session = payload["output"]["session"]

    assert len(session["timeline"]) >= 3
    assert len(session["mutation_history"]) == 1
    assert len(session["verification_history"]) == 1
