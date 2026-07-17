from __future__ import annotations

import json

from cli.zero_capability_detect import main, run
from core.runtime.runtime_capability_detection import CpuDetector


def test_defaults_and_list_do_not_detect(monkeypatch):
    monkeypatch.setattr(CpuDetector, "detect", lambda self, context: (_ for _ in ()).throw(AssertionError("detect called")))
    assert run(["defaults"])[1] == 0
    assert run(["list-detectors"])[1] == 0


def test_detect_output_and_validate(tmp_path):
    path = tmp_path / "detection.json"
    value, code = run(["detect", "--domain", "cpu", "--output", str(path), "--pretty"])
    assert code == 0 and json.loads(path.read_text(encoding="utf-8")) == value
    result, code = run(["validate", str(path)])
    assert code == 0 and result == {"valid": True, "errors": []}


def test_invalid_input_and_usage_exit_two(tmp_path):
    path = tmp_path / "invalid.json"; path.write_text("{}", encoding="utf-8")
    assert run(["validate", str(path)])[1] == 1
    assert run(["detect", "--domain", "not-a-domain"])[1] == 2
    assert main([]) == 2


def test_cli_output_contains_no_executable_path_or_provider_object(tmp_path):
    value, code = run(["detect", "--domain", "tools"])
    rendered = json.dumps(value)
    assert code == 0 and "object at" not in rendered and "executable_path" not in rendered

