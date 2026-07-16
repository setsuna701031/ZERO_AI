from cli.zero_capability import run as capability_run
from cli.zero_capability_strategy import build_parser, run


def test_select_validate_show_atomic_utf8(tmp_path):
    profile_path = tmp_path / "profile.json"
    _, code = capability_run(["detect", "--output", str(profile_path)]); assert code == 0
    output = tmp_path / "nested" / "strategy.json"
    strategy, code = run(["select", str(profile_path), "--output", str(output)])
    assert code == 0 and output.read_bytes()[:3] != b"\xef\xbb\xbf"
    result, code = run(["validate", str(output)]); assert code == 0 and result == {"valid": True, "errors": []}
    shown, code = run(["show", str(output)]); assert code == 0 and shown == strategy


def test_invalid_validation_and_input_exit_codes(tmp_path):
    invalid = tmp_path / "invalid.json"; invalid.write_text("{}", encoding="utf-8")
    assert run(["validate", str(invalid)])[1] == 1
    assert run(["select", str(tmp_path / "missing.json")])[1] == 2
    help_text = build_parser().format_help()
    assert all(term not in help_text for term in ("execute", "approve", "mutation", "commit"))
