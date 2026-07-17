from __future__ import annotations

import json

from cli.zero_capability_registry import main, run


def test_defaults_output_is_utf8_without_bom_and_valid(tmp_path):
    path = tmp_path / "registry.json"
    value, code = run(["defaults", "--output", str(path)])
    assert code == 0 and path.read_bytes().startswith(b"{")
    validated, code = run(["validate", str(path)])
    assert code == 0 and validated == {"valid": True, "errors": []}
    assert json.loads(path.read_text(encoding="utf-8")) == value


def test_resolve_returns_metadata_only_and_missing_is_one(tmp_path):
    path = tmp_path / "registry.json"; run(["defaults", "--output", str(path)])
    value, code = run(["resolve", str(path), "--kind", "detector", "--domain", "cpu"])
    assert code == 0 and value["found"] and value["entry"]["provider_ref"]
    assert "provider" not in value
    missing, code = run(["resolve", str(path), "--kind", "detector", "--domain", "missing"])
    assert code == 1 and missing == {"found": False, "entry": None}


def test_invalid_input_is_two_and_usage_is_two(tmp_path):
    path = tmp_path / "bad.json"; path.write_text("not-json", encoding="utf-8")
    assert run(["validate", str(path)])[1] == 2
    assert main([]) == 2

