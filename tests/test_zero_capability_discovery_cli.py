from __future__ import annotations

import json

from cli.zero_capability_discovery import main, run
from core.runtime.runtime_capability_detection import CpuDetector


def test_defaults_list_and_discover_never_detect(monkeypatch):
    monkeypatch.setattr(CpuDetector, "detect", lambda self, context: (_ for _ in ()).throw(AssertionError("detect called")))
    assert run(["defaults"])[1] == 0
    assert run(["list-providers"])[1] == 0
    value, code = run(["discover", "--domain", "cpu", "--platform-family", "linux"])
    assert code == 0 and value["selected_providers"][0]["domain"] == "cpu"


def test_discover_output_validate_and_explain(tmp_path):
    path = tmp_path / "discovery.json"
    value, code = run(["discover", "--domain", "cpu", "--output", str(path), "--pretty"])
    assert code == 0 and json.loads(path.read_text(encoding="utf-8")) == value
    assert run(["validate", str(path)]) == ({"valid": True, "errors": []}, 0)
    explained, code = run(["explain", "cpu"]); assert code == 0 and explained["selected"]


def test_invalid_inputs_and_safe_output(tmp_path):
    path = tmp_path / "bad.json"; path.write_text("{}", encoding="utf-8")
    assert run(["validate", str(path)])[1] == 1
    assert run(["discover", "--domain", "bad"])[1] == 2
    assert main([]) == 2
    rendered = json.dumps(run(["defaults"])[0]).casefold()
    assert "object at 0x" not in rendered and "hostname" not in rendered and "username" not in rendered
