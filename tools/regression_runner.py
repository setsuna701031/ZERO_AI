from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any, Sequence


TIERS: dict[str, dict[str, Any]] = {
    "smoke": {
        "name": "smoke",
        "description": "daily fastest release smoke tests",
        "owner": "regression-governance",
        "expected_duration": "<1 minute",
        "includes": ("smoke",),
        "marker_expression": "smoke",
        "pytest_args": ("-m", "smoke", "-q"),
    },
    "contract": {
        "name": "contract",
        "description": "fast mainline contract tests",
        "owner": "regression-governance",
        "expected_duration": "<3 minutes",
        "includes": ("contract_fast",),
        "marker_expression": "contract_fast",
        "pytest_args": ("-m", "contract_fast", "-q"),
    },
    "contract-fast": {
        "name": "contract-fast",
        "description": "fast helper/runtime/authority/parser/payload/state/registry contract tests",
        "owner": "regression-governance",
        "expected_duration": "<3 minutes",
        "includes": ("contract_fast",),
        "marker_expression": "contract_fast",
        "pytest_args": ("-m", "contract_fast", "-q"),
    },
    "contract-heavy": {
        "name": "contract-heavy",
        "description": "heavy contract tests involving inventory, scans, traversal, subprocess, CLI, or repository inspection",
        "owner": "regression-governance",
        "expected_duration": ">3 minutes",
        "includes": ("contract_heavy",),
        "marker_expression": "contract_heavy",
        "pytest_args": ("-m", "contract_heavy", "-q"),
        "warning": "contract-heavy can include repository traversal, subprocess, and inventory tests",
    },
    "fast": {
        "name": "fast",
        "description": "fast local regression limited to smoke and fast contract tests",
        "owner": "regression-governance",
        "expected_duration": "<3 minutes",
        "includes": ("smoke", "contract_fast"),
        "marker_expression": "smoke or contract_fast",
        "pytest_args": ("-m", "smoke or contract_fast", "-q"),
    },
    "integration": {
        "name": "integration",
        "description": "integration tests, including slow tests when they carry the integration marker",
        "owner": "regression-governance",
        "expected_duration": "variable",
        "includes": ("integration",),
        "marker_expression": "integration",
        "pytest_args": ("-m", "integration", "-q"),
        "warning": "integration may include slow tests and can take a while",
    },
    "llm": {
        "name": "llm",
        "description": "LLM/Ollama/external service tests",
        "owner": "regression-governance",
        "expected_duration": "variable",
        "includes": ("llm", "external"),
        "marker_expression": "llm or external",
        "pytest_args": ("-m", "llm or external", "-q"),
        "confirm_flag": "confirm_external",
        "warning": "llm includes external/service-facing tests; pass --confirm-external to execute",
    },
    "nightly": {
        "name": "nightly",
        "description": "governed nightly regression across marked local tiers",
        "owner": "regression-governance",
        "expected_duration": "long",
        "includes": ("smoke", "contract_fast", "contract_heavy", "integration", "slow"),
        # TODO(regression-governance): expand this expression only after marker
        # coverage is complete; nightly must stay governed instead of falling
        # back to an implicit broad full-suite selection.
        "marker_expression": "smoke or contract_fast or contract_heavy or integration or slow",
        "pytest_args": ("-m", "smoke or contract_fast or contract_heavy or integration or slow", "-q"),
        "confirm_flag": "confirm_nightly",
        "warning": (
            "nightly is marker-governed and may be incomplete until all tests are tiered; "
            "pass --confirm-nightly to execute"
        ),
    },
    "full": {
        "name": "full",
        "description": "explicit full pytest suite",
        "owner": "regression-governance",
        "expected_duration": "long",
        "includes": ("all pytest-collected tests",),
        "pytest_args": ("tests", "-q"),
        "confirm_flag": "confirm_nightly",
        "warning": "full runs the broad pytest suite; pass --confirm-nightly to execute",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ZERO pytest regression tiers.",
    )
    parser.add_argument("tier", help="Regression tier to run, or 'list'.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the pytest command without executing it.",
    )
    parser.add_argument(
        "--confirm-nightly",
        action="store_true",
        help="Required to execute the nightly tier.",
    )
    parser.add_argument(
        "--confirm-external",
        action="store_true",
        help="Required to execute the llm/external tier.",
    )
    return parser


def shell_quote(part: str) -> str:
    if not part:
        return '""'
    if any(char.isspace() for char in part) or '"' in part:
        return '"' + part.replace('"', '\\"') + '"'
    return part


def format_command(command: Sequence[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def get_tier(name: str) -> dict[str, Any] | None:
    return TIERS.get(name)


def build_pytest_command(tier: dict[str, Any], executable: str = sys.executable) -> list[str]:
    return [executable, "-m", "pytest", *tier["pytest_args"]]


def format_available_tiers() -> str:
    lines = ["Available regression tiers:"]
    for tier in TIERS.values():
        marker = tier.get("marker_expression") or "explicit pytest args"
        lines.extend(
            [
                f"- {tier['name']}",
                f"  description: {tier['description']}",
                f"  owner: {tier['owner']}",
                f"  expected_duration: {tier['expected_duration']}",
                f"  includes: {', '.join(tier['includes'])}",
                f"  marker_or_args: {marker}",
            ]
        )
    return "\n".join(lines)


def print_tier_list() -> None:
    print(format_available_tiers(), flush=True)


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.tier == "list":
        print_tier_list()
        return 0

    tier = get_tier(args.tier)
    if tier is None:
        print(f"Unknown regression tier: {args.tier}", flush=True)
        print_tier_list()
        return 2

    command = build_pytest_command(tier)

    print(f"Tier: {tier['name']}", flush=True)
    print(f"Description: {tier['description']}", flush=True)
    if tier.get("warning"):
        print(f"Warning: {tier['warning']}", flush=True)
    print(f"Pytest command: {format_command(command)}", flush=True)

    if args.dry_run:
        print("Dry run: command not executed.", flush=True)
        return 0

    confirm_flag = tier.get("confirm_flag")
    if confirm_flag and not getattr(args, confirm_flag):
        required = "--confirm-nightly" if confirm_flag == "confirm_nightly" else "--confirm-external"
        print(f"Refusing to run {tier['name']}: pass {required} to execute this tier.", flush=True)
        return 2

    result = subprocess.run(command)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(run())
