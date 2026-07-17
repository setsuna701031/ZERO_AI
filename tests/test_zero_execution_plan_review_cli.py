from __future__ import annotations

import json

from cli.zero_execution_plan_review import run_execution_plan_review_cli
from tests.test_runtime_execution_plan_review_gate import NOW, plan, review


def write(path, value, bom=False):
    path.write_text(json.dumps(value), encoding="utf-8-sig" if bom else "utf-8")


def test_build_approved_rejected_status_and_result_path(tmp_path):
    p = plan(); pp, rp = tmp_path / "plan.json", tmp_path / "review.json"
    write(pp, p, bom=True); write(rp, review(p), bom=True)
    out = tmp_path / "nested" / "result.json"
    approved, code = run_execution_plan_review_cli("build", pp, rp, now=NOW, result_path=out)
    assert code == 0 and approved["review_status"] == "approved"
    assert json.loads(out.read_text(encoding="utf-8")) == approved
    status, code = run_execution_plan_review_cli("status", out, result_path=out)
    assert code == 0 and status["review_status"] == "approved"
    write(rp, review(p, "rejected"))
    rejected, code = run_execution_plan_review_cli("build", pp, rp, now=NOW, result_path=out)
    assert code == 1 and rejected["review_status"] == "rejected"
    status, code = run_execution_plan_review_cli("status", out, result_path=out)
    assert code == 0 and status["review_status"] == "rejected"


def test_invalid_json_expired_and_invalid_status(tmp_path):
    p = plan(); pp, rp, out = tmp_path / "p.json", tmp_path / "r.json", tmp_path / "out.json"
    write(pp, p); rp.write_text("bad", encoding="utf-8")
    _, code = run_execution_plan_review_cli("build", pp, rp, now=NOW, result_path=out)
    assert code == 2
    write(rp, review(p))
    result, code = run_execution_plan_review_cli("build", pp, rp,
        now="2026-07-10T13:00:00+00:00", result_path=out)
    assert code == 1 and "review_expired" in result["reasons"]
    write(out, {"contract": "wrong"})
    result, code = run_execution_plan_review_cli("status", out, result_path=out)
    assert code == 2 and result["execution_allowed"] is False
