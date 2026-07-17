from pathlib import Path

from cli.zero_capability import build_parser, run


def test_detect_validate_show_and_atomic_utf8_output(tmp_path: Path):
    output = tmp_path / "nested" / "profile.json"
    profile, code = run(["detect", "--output", str(output)])
    assert code == 0 and output.read_bytes()[:3] != b"\xef\xbb\xbf"
    validated, code = run(["validate", str(output)])
    assert code == 0 and validated == {"valid": True, "errors": []}
    shown, code = run(["show", str(output)])
    assert code == 0 and shown == profile


def test_invalid_profile_and_usage_codes(tmp_path: Path):
    invalid = tmp_path / "invalid.json"; invalid.write_text("{}", encoding="utf-8")
    assert run(["validate", str(invalid)])[1] == 1
    assert run(["show", str(tmp_path / "missing.json")])[1] == 2
    help_text = build_parser().format_help()
    assert all(term not in help_text for term in ("execute", "approve", "mutation", "commit"))
