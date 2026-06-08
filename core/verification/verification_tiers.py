from __future__ import annotations

"""Tiered verification command manifest and runner."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_SKIPPED_BY_TIER = "skipped_by_tier"

FAST_TIER = "fast"
CONTRACT_TIER = "contract"
FULL_TIER = "full"
LONG_TIER = "long"
ALL_TIER = "all"

TIERS = (FAST_TIER, CONTRACT_TIER, FULL_TIER, LONG_TIER)


@dataclass(frozen=True)
class VerificationCommand:
    label: str
    tier: str
    args: tuple[str, ...]
    timeout_seconds: int = 600
    optional: bool = False
    long_demo: bool = False
    legacy_diagnostic_output: bool = False

    def argv(self, python_executable: str | None = None) -> list[str]:
        return [python_executable or sys.executable, *self.args]

    def command_text(self) -> str:
        return " ".join(("python", *self.args))


@dataclass(frozen=True)
class VerificationResult:
    label: str
    tier: str
    command: str
    status: str
    returncode: int | None = None
    timeout_seconds: int | None = None
    optional: bool = False
    long_demo: bool = False
    legacy_diagnostic_output: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        if self.status in {STATUS_PASSED, STATUS_SKIPPED_BY_TIER}:
            return True
        if self.optional and self.status in {STATUS_FAILED, STATUS_TIMEOUT}:
            return True
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "tier": self.tier,
            "command": self.command,
            "status": self.status,
            "returncode": self.returncode,
            "timeout_seconds": self.timeout_seconds,
            "optional": self.optional,
            "long_demo": self.long_demo,
            "legacy_diagnostic_output": self.legacy_diagnostic_output,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


VERIFICATION_TIERS: tuple[VerificationCommand, ...] = (
    VerificationCommand(
        label="verification tier tests",
        tier=FAST_TIER,
        args=("-m", "pytest", "tests/test_verification_tiers.py"),
        timeout_seconds=120,
    ),
    VerificationCommand(
        label="decision evidence viewer tests",
        tier=FAST_TIER,
        args=("-m", "pytest", "tests/test_decision_evidence_viewer.py"),
        timeout_seconds=120,
    ),
    VerificationCommand(
        label="tool layer smoke",
        tier=FAST_TIER,
        args=("tests/run_tool_layer_smoke.py",),
        timeout_seconds=120,
    ),
    VerificationCommand(
        label="runtime smoke",
        tier=CONTRACT_TIER,
        args=("tests/run_runtime_smoke.py",),
        timeout_seconds=420,
    ),
    VerificationCommand(
        label="executor smoke",
        tier=FAST_TIER,
        args=("tests/run_executor_smoke.py",),
        timeout_seconds=180,
    ),
    VerificationCommand(
        label="scheduler smoke",
        tier=FAST_TIER,
        args=("tests/run_scheduler_smoke.py",),
        timeout_seconds=420,
    ),
    VerificationCommand(
        label="control and evidence contracts",
        tier=CONTRACT_TIER,
        args=(
            "-m",
            "pytest",
            "tests/test_task_control_api.py",
            "tests/test_task_lifecycle_monitor.py",
            "tests/test_decision_evidence_layer.py",
            "tests/test_decision_evidence_viewer.py",
            "tests/test_adaptive_planning_foundation.py",
            "tests/test_demo_authority_continuity.py",
            "tests/test_runtime_execution_result_contract.py",
            "tests/test_scheduler_taskrunner_authority_propagation_contract.py",
            "tests/test_governed_repair_mutation_policy_smoke.py",
        ),
        timeout_seconds=900,
    ),
    VerificationCommand(
        label="AER workflow runtime session contract",
        tier=CONTRACT_TIER,
        args=("tests/test_runtime_workflow_session_contract.py",),
        timeout_seconds=180,
    ),
    VerificationCommand(
        label="agent loop smoke",
        tier=CONTRACT_TIER,
        args=("tests/run_agent_loop_smoke.py",),
        timeout_seconds=180,
        optional=True,
        legacy_diagnostic_output=True,
    ),
    VerificationCommand(
        label="implementation-proof smoke",
        tier=CONTRACT_TIER,
        args=("tests/run_implementation_proof_smoke.py",),
        timeout_seconds=600,
    ),
    VerificationCommand(
        label="full pytest",
        tier=FULL_TIER,
        args=("-m", "pytest"),
        timeout_seconds=7200,
    ),
    VerificationCommand(
        label="document task smoke",
        tier=LONG_TIER,
        args=("tests/run_document_task_smoke.py",),
        timeout_seconds=1800,
        long_demo=True,
    ),
    VerificationCommand(
        label="document flow showcase smoke",
        tier=LONG_TIER,
        args=("tests/run_document_flow_showcase_smoke.py",),
        timeout_seconds=1800,
        long_demo=True,
    ),
    VerificationCommand(
        label="document pipeline identity smoke",
        tier=LONG_TIER,
        args=("tests/run_document_pipeline_identity_smoke.py",),
        timeout_seconds=1800,
        long_demo=True,
    ),
    VerificationCommand(
        label="requirement demo smoke",
        tier=LONG_TIER,
        args=("tests/run_requirement_demo_smoke.py",),
        timeout_seconds=1800,
        long_demo=True,
    ),
    VerificationCommand(
        label="execution demo smoke",
        tier=LONG_TIER,
        args=("tests/run_execution_demo_smoke.py",),
        timeout_seconds=1800,
        long_demo=True,
    ),
    VerificationCommand(
        label="semantic task smoke",
        tier=LONG_TIER,
        args=("tests/run_semantic_task_smoke.py",),
        timeout_seconds=2400,
        long_demo=True,
    ),
    VerificationCommand(
        label="full-build-demo smoke",
        tier=LONG_TIER,
        args=("tests/run_full_build_demo_smoke.py",),
        timeout_seconds=2400,
        long_demo=True,
    ),
    VerificationCommand(
        label="long goal validation",
        tier=LONG_TIER,
        args=(
            "-m",
            "pytest",
            "tests/validation/test_long_running_engineering_goal_v1.py",
            "tests/validation/test_long_running_engineering_goal_v2.py",
        ),
        timeout_seconds=1800,
        long_demo=True,
    ),
)


MAINLINE_CHILD_COMMANDS: tuple[VerificationCommand, ...] = tuple(
    command
    for command in VERIFICATION_TIERS
    if command.label
    in {
        "tool layer smoke",
        "scheduler smoke",
        "runtime smoke",
        "document task smoke",
        "document flow showcase smoke",
        "document pipeline identity smoke",
        "requirement demo smoke",
        "execution demo smoke",
        "semantic task smoke",
        "implementation-proof smoke",
        "full-build-demo smoke",
        "agent loop smoke",
        "executor smoke",
        "AER workflow runtime session contract",
    }
)


CommandRunner = Callable[[VerificationCommand, Path], VerificationResult]


def selected_commands(tier: str) -> list[VerificationCommand]:
    normalized = str(tier or "").strip().lower()
    if normalized == ALL_TIER:
        return list(VERIFICATION_TIERS)
    if normalized not in TIERS:
        raise ValueError(f"unknown_verification_tier:{tier}")
    return [command for command in VERIFICATION_TIERS if command.tier == normalized]


def skipped_commands(tier: str) -> list[VerificationCommand]:
    normalized = str(tier or "").strip().lower()
    if normalized == ALL_TIER:
        return []
    selected = set(selected_commands(normalized))
    return [command for command in VERIFICATION_TIERS if command not in selected]


def _skipped_result(command: VerificationCommand) -> VerificationResult:
    return VerificationResult(
        label=command.label,
        tier=command.tier,
        command=command.command_text(),
        status=STATUS_SKIPPED_BY_TIER,
        timeout_seconds=command.timeout_seconds,
        optional=command.optional,
        long_demo=command.long_demo,
        legacy_diagnostic_output=command.legacy_diagnostic_output,
    )


def run_tier(
    tier: str,
    *,
    repo_root: str | Path | None = None,
    runner: CommandRunner | None = None,
    include_skipped: bool = True,
) -> dict[str, object]:
    normalized = str(tier or "").strip().lower()
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    if runner is None:
        raise ValueError("verification_runner_required")
    run_one = runner
    results: list[VerificationResult] = []

    for command in selected_commands(normalized):
        results.append(run_one(command, root))

    if include_skipped:
        results.extend(_skipped_result(command) for command in skipped_commands(normalized))

    selected_results = [result for result in results if result.status != STATUS_SKIPPED_BY_TIER]
    blocking = [
        result
        for result in selected_results
        if result.status in {STATUS_FAILED, STATUS_TIMEOUT} and not result.optional
    ]
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    return {
        "ok": not blocking,
        "tier": normalized,
        "repo_root": str(root),
        "status_counts": status_counts,
        "results": [result.to_dict() for result in results],
        "blocking_results": [result.to_dict() for result in blocking],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python main.py verify")
    parser.add_argument("tier", choices=(*TIERS, ALL_TIER))
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--no-skipped", action="store_true")
    return parser


def tier_commands(tier: str) -> list[str]:
    return [command.command_text() for command in selected_commands(tier)]


__all__ = [
    "ALL_TIER",
    "CONTRACT_TIER",
    "FAST_TIER",
    "FULL_TIER",
    "LONG_TIER",
    "MAINLINE_CHILD_COMMANDS",
    "STATUS_FAILED",
    "STATUS_PASSED",
    "STATUS_SKIPPED_BY_TIER",
    "STATUS_TIMEOUT",
    "TIERS",
    "VERIFICATION_TIERS",
    "VerificationCommand",
    "VerificationResult",
    "run_tier",
    "selected_commands",
    "skipped_commands",
    "tier_commands",
]
