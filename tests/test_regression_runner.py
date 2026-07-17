from __future__ import annotations

import sys

from tools import regression_runner


def test_fast_command_is_unchanged() -> None:
    command = regression_runner.build_pytest_command(
        regression_runner.TIERS["fast"],
        executable="python",
    )

    assert command == [
        "python",
        "-m",
        "pytest",
        "-m",
        "smoke or contract_fast",
        "-q",
    ]


def test_contract_command_uses_contract_fast() -> None:
    command = regression_runner.build_pytest_command(
        regression_runner.TIERS["contract"],
        executable="python",
    )

    assert command == ["python", "-m", "pytest", "-m", "contract_fast", "-q"]


def test_tier_metadata_is_centralized() -> None:
    required = {"fast", "contract", "nightly", "llm", "full"}

    assert required.issubset(regression_runner.TIERS)
    for name in required:
        tier = regression_runner.TIERS[name]
        assert tier["name"] == name
        assert tier["description"]
        assert tier["owner"]
        assert tier["expected_duration"]
        assert tier["includes"]
        assert tier["pytest_args"]


def test_nightly_is_marker_governed_not_full_suite() -> None:
    tier = regression_runner.TIERS["nightly"]

    assert tier["marker_expression"] == "smoke or contract_fast or contract_heavy or integration or slow"
    assert tier["pytest_args"] == ("-m", tier["marker_expression"], "-q")
    assert "tests" not in tier["pytest_args"]


def test_full_is_explicit_broad_suite() -> None:
    tier = regression_runner.TIERS["full"]

    assert tier.get("marker_expression") is None
    assert tier["pytest_args"] == ("tests", "-q")


def test_get_tier_returns_registry_entry() -> None:
    assert regression_runner.get_tier("fast") is regression_runner.TIERS["fast"]
    assert regression_runner.get_tier("missing-tier") is None


def test_invalid_tier_prints_available_tiers(capsys) -> None:
    result = regression_runner.run(["missing-tier"])

    captured = capsys.readouterr()
    assert result == 2
    assert "Unknown regression tier" in captured.out
    assert "Available regression tiers:" in captured.out
    assert "- fast" in captured.out


def test_dry_run_uses_shared_command_builder(capsys) -> None:
    result = regression_runner.run(["fast", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert (
        f"{sys.executable} -m pytest -m \"smoke or contract_fast\" -q"
        in captured.out
    )
