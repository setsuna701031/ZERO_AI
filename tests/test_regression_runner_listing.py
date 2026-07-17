from __future__ import annotations

from tools import regression_runner


def test_list_command_prints_all_tier_metadata(capsys) -> None:
    result = regression_runner.run(["list"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Available regression tiers:" in captured.out

    for name in ("fast", "contract", "nightly", "llm", "full"):
        assert f"- {name}" in captured.out
        assert "description:" in captured.out
        assert "owner:" in captured.out
        assert "expected_duration:" in captured.out
        assert "includes:" in captured.out
        assert "marker_or_args:" in captured.out


def test_format_available_tiers_includes_fast_expression() -> None:
    output = regression_runner.format_available_tiers()

    assert "- fast" in output
    assert "marker_or_args: smoke or contract_fast" in output
