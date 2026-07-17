from __future__ import annotations

import json

from cli.zero_controlled_apply_admission import run_controlled_apply_admission_cli
from tests.test_runtime_controlled_apply_admission import NOW, approval, proposal


def write(path, value): path.write_text(json.dumps(value), encoding="utf-8")


def test_admit_status_and_result_file(tmp_path):
    p = proposal(); a = approval(p)
    pp, ap, out = tmp_path / "p.json", tmp_path / "a.json", tmp_path / "out.json"
    write(pp, p); write(ap, a)
    result, code = run_controlled_apply_admission_cli(
        "admit", pp, ap, controlled=True, now=NOW, result_path=out)
    assert code == 0 and result["apply_admitted"] is True
    assert json.loads(out.read_text(encoding="utf-8")) == result
    status, code = run_controlled_apply_admission_cli("status", out, result_path=out)
    assert code == 0 and status["admission_status"] == "admitted"


def test_denied_and_input_errors(tmp_path):
    pp, ap, out = tmp_path / "p.json", tmp_path / "a.json", tmp_path / "out.json"
    p = proposal(); write(pp, p); write(ap, approval(p))
    result, code = run_controlled_apply_admission_cli("admit", pp, ap, result_path=out)
    assert code == 1 and result["admission_status"] == "denied_uncontrolled_mode"
    pp.write_text("not json", encoding="utf-8")
    result, code = run_controlled_apply_admission_cli("admit", pp, ap, controlled=True, result_path=out)
    assert code == 2 and result["admission_status"] == "input_error"
