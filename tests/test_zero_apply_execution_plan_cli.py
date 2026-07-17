from __future__ import annotations

import copy
import json

from cli.zero_apply_execution_plan import run_apply_execution_plan_cli
from tests.test_runtime_apply_execution_plan_builder import NOW, lineage


def write(path, value): path.write_text(json.dumps(value), encoding="utf-8")


def test_build_status_result_and_source_purity(tmp_path):
    p, a, d = lineage(); before = copy.deepcopy((p, a, d))
    paths = [tmp_path / name for name in ("p.json", "a.json", "d.json")]
    for path, value in zip(paths, (p, a, d)): write(path, value)
    out = tmp_path / "nested" / "plan.json"
    result, code = run_apply_execution_plan_cli("build", *paths, now=NOW, result_path=out)
    assert code == 0 and result["plan_ready"] is True
    assert json.loads(out.read_text(encoding="utf-8")) == result
    status, code = run_apply_execution_plan_cli("status", out, result_path=out)
    assert code == 0 and status["plan_status"] == "ready"
    assert (p, a, d) == before


def test_denied_missing_and_invalid_json_exit_codes(tmp_path):
    p, a, d = lineage(); a["revoked"] = True
    paths = [tmp_path / name for name in ("p.json", "a.json", "d.json")]
    for path, value in zip(paths, (p, a, d)): write(path, value)
    result, code = run_apply_execution_plan_cli("build", *paths, result_path=tmp_path / "out.json")
    assert code == 1 and result["plan_status"] == "denied_revoked"
    paths[0].unlink()
    _, code = run_apply_execution_plan_cli("build", *paths, result_path=tmp_path / "out.json")
    assert code == 2
    paths[0].write_text("bad json", encoding="utf-8")
    result, code = run_apply_execution_plan_cli("build", *paths, result_path=tmp_path / "out.json")
    assert code == 2 and result["plan_status"] == "input_error"
