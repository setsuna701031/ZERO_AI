from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Tier:
    name: str
    pytest_args: tuple[str, ...]
    description: str
    confirm_flag: str | None = None
    warning: str | None = None


TIERS: dict[str, Tier] = {
    "smoke": Tier(
        name="smoke",
        pytest_args=("-m", "smoke", "-q"),
        description="daily fastest release smoke tests",
    ),
    "contract": Tier(
        name="contract",
        pytest_args=(
            "-m",
            "contract and not slow and not integration and not external and not llm",
            "-q",
        ),
        description="mainline contract tests excluding slow, integration, external, and llm tiers",
    ),
    "fast": Tier(
        name="fast",
        pytest_args=(
            "tests",
            "-q",
            "-m",
            "not integration and not external and not llm and not slow",
        ),
        description="fast local regression excluding integration, external, llm, and slow tiers",
    ),
    "integration": Tier(
        name="integration",
        pytest_args=("-m", "integration", "-q"),
        description="integration tests, including slow tests when they carry the integration marker",
        warning="integration may include slow tests and can take a while",
    ),
    "llm": Tier(
        name="llm",
        pytest_args=("-m", "llm or external", "-q"),
        description="LLM/Ollama/external service tests",
        confirm_flag="confirm_external",
        warning="llm includes external/service-facing tests; pass --confirm-external to execute",
    ),
    "nightly": Tier(
        name="nightly",
        pytest_args=("tests", "-q"),
        description="full nightly regression suite",
        confirm_flag="confirm_nightly",
        warning="nightly runs the full test suite; pass --confirm-nightly to execute",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ZERO pytest regression tiers.",
    )
    parser.add_argument(
        "tier",
        choices=tuple(TIERS),
        help="Regression tier to run.",
    )
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


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    tier = TIERS[args.tier]
    command = [sys.executable, "-m", "pytest", *tier.pytest_args]

    print(f"Tier: {tier.name}", flush=True)
    print(f"Description: {tier.description}", flush=True)
    if tier.warning:
        print(f"Warning: {tier.warning}", flush=True)
    print(f"Pytest command: {format_command(command)}", flush=True)

    if args.dry_run:
        print("Dry run: command not executed.", flush=True)
        return 0

    if tier.confirm_flag and not getattr(args, tier.confirm_flag):
        required = "--confirm-nightly" if tier.confirm_flag == "confirm_nightly" else "--confirm-external"
        print(f"Refusing to run {tier.name}: pass {required} to execute this tier.", flush=True)
        return 2

    result = subprocess.run(command)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(run())
