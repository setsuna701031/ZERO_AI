from __future__ import annotations

import json

from cli.zero_controlled_execution import run_controlled_execution_cli
from tests.test_runtime_executor_admission_token import NOW, inputs


def write(path, value, bom=False): path.write_text(json.dumps(value), encoding="utf-8-sig" if bom else "utf-8")


def test_run_status_bom_result_and_no_target_mutation(tmp_path):
    (tmp_path / "workspace").mkdir(); target = tmp_path / "workspace" / "a.txt"; target.write_text("same")
    p, r, q = inputs(tmp_path); paths = [tmp_path / name for name in ("p.json", "r.json", "q.json")]
    for path, value in zip(paths, (p, r, q)): write(path, value, bom=True)
    before = target.read_bytes(); out = tmp_path / "result.json"
    result, code = run_controlled_execution_cli("run", *paths, target_root=tmp_path, now=NOW, result_path=out)
    assert code == 0 and result["activation_status"] == "completed" and target.read_bytes() == before
    status, code = run_controlled_execution_cli("status", out, result_path=out)
    assert code == 0 and status["activation_status"] == "completed"


def test_blocked_and_input_errors(tmp_path):
    p, r, q = inputs(tmp_path); q["requested_mode"] = "active"
    paths = [tmp_path / name for name in ("p.json", "r.json", "q.json")]
    for path, value in zip(paths, (p, r, q)): write(path, value)
    out = tmp_path / "out.json"
    result, code = run_controlled_execution_cli("run", *paths, target_root=tmp_path, now=NOW, result_path=out)
    assert code == 1 and result["activation_status"] == "blocked"
    paths[0].write_text("bad", encoding="utf-8")
    _, code = run_controlled_execution_cli("run", *paths, target_root=tmp_path, result_path=out)
    assert code == 2
    write(out, {"contract": "wrong"})
    _, code = run_controlled_execution_cli("status", out, result_path=out)
    assert code == 2
