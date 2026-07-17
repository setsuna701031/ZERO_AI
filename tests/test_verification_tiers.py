from __future__ import annotations

from pathlib import Path

import main as zero_main
from cli import verification_cli
from core.verification import verification_tiers as tiers


LONG_NEEDLES = {
    "document task smoke",
    "semantic task smoke",
    "requirement demo smoke",
    "full-build-demo smoke",
}


def _passing_runner(command: tiers.VerificationCommand, repo_root: Path) -> tiers.VerificationResult:
    return tiers.VerificationResult(
        label=command.label,
        tier=command.tier,
        command=command.command_text(),
        status=tiers.STATUS_PASSED,
        returncode=0,
        timeout_seconds=command.timeout_seconds,
        optional=command.optional,
        long_demo=command.long_demo,
        legacy_diagnostic_output=command.legacy_diagnostic_output,
    )


def test_long_demos_are_not_in_fast_smoke() -> None:
    fast = tiers.selected_commands(tiers.FAST_TIER)

    assert all(command.long_demo is False for command in fast)
    assert LONG_NEEDLES.isdisjoint({command.label for command in fast})


def test_fast_smoke_command_does_not_call_long_demo_commands(tmp_path: Path) -> None:
    called: list[str] = []

    def runner(command: tiers.VerificationCommand, repo_root: Path) -> tiers.VerificationResult:
        called.append(command.label)
        return _passing_runner(command, repo_root)

    payload = tiers.run_tier(tiers.FAST_TIER, repo_root=tmp_path, runner=runner)

    assert payload["ok"] is True
    assert LONG_NEEDLES.isdisjoint(set(called))
    skipped = {
        item["label"]: item["status"]
        for item in payload["results"]
        if item["label"] in LONG_NEEDLES
    }
    assert skipped
    assert set(skipped.values()) == {tiers.STATUS_SKIPPED_BY_TIER}


def test_each_tier_reports_command_status_clearly(tmp_path: Path) -> None:
    payload = tiers.run_tier(tiers.CONTRACT_TIER, repo_root=tmp_path, runner=_passing_runner)

    selected = [item for item in payload["results"] if item["status"] != tiers.STATUS_SKIPPED_BY_TIER]
    assert payload["ok"] is True
    assert selected
    assert all(item["status"] == tiers.STATUS_PASSED for item in selected)
    assert all(item["command"].startswith("python ") for item in selected)
    assert payload["status_counts"][tiers.STATUS_PASSED] == len(selected)


def test_timeout_is_reported_as_timeout_not_failure(tmp_path: Path) -> None:
    def runner(command: tiers.VerificationCommand, repo_root: Path) -> tiers.VerificationResult:
        if command.label == "executor smoke":
            return tiers.VerificationResult(
                label=command.label,
                tier=command.tier,
                command=command.command_text(),
                status=tiers.STATUS_TIMEOUT,
                timeout_seconds=command.timeout_seconds,
            )
        return _passing_runner(command, repo_root)

    payload = tiers.run_tier(tiers.FAST_TIER, repo_root=tmp_path, runner=runner, include_skipped=False)
    timeout_items = [item for item in payload["results"] if item["status"] == tiers.STATUS_TIMEOUT]

    assert payload["ok"] is False
    assert len(timeout_items) == 1
    assert timeout_items[0]["label"] == "executor smoke"
    assert timeout_items[0]["status"] != tiers.STATUS_FAILED
    assert payload["blocking_results"][0]["status"] == tiers.STATUS_TIMEOUT


def test_skipped_by_tier_is_explicit(tmp_path: Path) -> None:
    payload = tiers.run_tier(tiers.FAST_TIER, repo_root=tmp_path, runner=_passing_runner)

    skipped = [item for item in payload["results"] if item["status"] == tiers.STATUS_SKIPPED_BY_TIER]

    assert skipped
    assert any(item["long_demo"] is True for item in skipped)
    assert all(item["status"] != tiers.STATUS_PASSED for item in skipped)


def test_main_py_smoke_maps_to_fast_tier(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    def fake_cli(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(verification_cli, "run_verification_cli", fake_cli)

    exit_code = zero_main.main(["main.py", "smoke"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [["fast"]]
    assert "fast verification tier" in output


def test_mainline_children_are_classified_without_long_demos_in_fast() -> None:
    child_labels = {command.label for command in tiers.MAINLINE_CHILD_COMMANDS}

    assert "document task smoke" in child_labels
    assert "full-build-demo smoke" in child_labels
    assert "scheduler smoke" in child_labels
    assert all(
        command.tier != tiers.FAST_TIER
        for command in tiers.MAINLINE_CHILD_COMMANDS
        if command.long_demo
    )
