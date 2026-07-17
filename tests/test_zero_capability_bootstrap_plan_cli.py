from __future__ import annotations

import json

from cli.zero_capability_bootstrap_plan import main, run
from tests.test_runtime_capability_bootstrap_plan import make_plan


def write(path, value): path.write_text(json.dumps(value), encoding="utf-8")


def test_defaults_scopes_plan_validate_and_explain(tmp_path):
    assert run(["defaults"])[1] == 0 and run(["scopes"])[1] == 0
    _, artifacts = make_plan(); d, det, p, s, provenance, policy, _ = artifacts
    paths = {}
    for name, value in (("discovery", d), ("detection", det), ("profile", p), ("strategy", s), ("provenance", provenance), ("policy", policy)):
        paths[name] = tmp_path / f"{name}.json"; write(paths[name], value)
    output = tmp_path / "plan.json"
    args = ["plan"] + [part for name in ("discovery", "detection", "profile", "strategy", "provenance", "policy") for part in (f"--{name}", str(paths[name]))] + ["--output", str(output), "--pretty"]
    value, code = run(args); assert code == 0 and json.loads(output.read_text(encoding="utf-8")) == value
    assert run(["validate", str(output)]) == ({"valid": True, "errors": []}, 0)
    explained, code = run(["explain", str(output)]); assert code == 0 and explained["readiness"] == "ready" and explained["steps"]


def test_invalid_cli_input_and_no_execute_command(tmp_path):
    path = tmp_path / "bad.json"; path.write_text("{}", encoding="utf-8")
    assert run(["validate", str(path)])[1] == 1
    assert main([]) == 2 and main(["execute"]) == 2
