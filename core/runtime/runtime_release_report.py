from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import re
import subprocess
from typing import Any

from core.operator.runtime_operator_dashboard import VERSION as DASHBOARD_VERSION
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


CONTRACT = "zero.runtime.release_report.v1"
RUNTIME_RELEASE_VERSION = "1.0.0-rc.1"
MANIFEST_VERSION = "zero.runtime.freeze-manifest.v1"
INVARIANT_VERSION = "zero.runtime.invariants.v1"
UPGRADE_FIXTURE_VERSION = "runtime-rc-v1"


@dataclass(frozen=True)
class RuntimeReleaseReport:
    runtime_version: str
    git_commit: str
    release_timestamp: str
    manifest_version: str
    invariant_version: str
    dashboard_version: str
    contract_version: str
    upgrade_fixture_version: str
    kernel_version: str
    contract: str = CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _git_value(root: Path, format_value: str) -> str | None:
    from core.runtime.executor import run_canonical_subprocess

    try:
        result = run_canonical_subprocess(
            ["git", "show", "-s", f"--format={format_value}", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def generate_runtime_release_report(repository_root: str | Path = ".") -> RuntimeReleaseReport:
    root = Path(repository_root).resolve(strict=True)
    commit = _git_value(root, "%H") or "unavailable"
    if commit != "unavailable" and not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        commit = "unavailable"
    release_timestamp = _git_value(root, "%cI") or "1970-01-01T00:00:00Z"
    return RuntimeReleaseReport(
        runtime_version=RUNTIME_RELEASE_VERSION,
        git_commit=commit,
        release_timestamp=release_timestamp,
        manifest_version=MANIFEST_VERSION,
        invariant_version=INVARIANT_VERSION,
        dashboard_version=DASHBOARD_VERSION,
        contract_version=RUNTIME_ABI_VERSION,
        upgrade_fixture_version=UPGRADE_FIXTURE_VERSION,
        kernel_version=RUNTIME_KERNEL_VERSION,
    )


def main() -> int:
    print(generate_runtime_release_report().to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONTRACT",
    "DASHBOARD_VERSION",
    "INVARIANT_VERSION",
    "MANIFEST_VERSION",
    "RUNTIME_RELEASE_VERSION",
    "UPGRADE_FIXTURE_VERSION",
    "RuntimeReleaseReport",
    "generate_runtime_release_report",
    "main",
]
