from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path.cwd()
BASE = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
STAGE5_MAPPING = BASE / "runtime_contract_ownership_mapping_stage5.json"
STAGE5_SUMMARY = BASE / "runtime_contract_ownership_mapping_stage5_summary.json"
OUT_JSON = BASE / "runtime_native_contract_test_specs_stage6.json"
OUT_SUMMARY = BASE / "runtime_native_contract_test_specs_stage6_summary.json"
OUT_REPORT = BASE / "runtime_native_contract_test_specs_stage6_report.md"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for key in ("items", "mapping", "contracts", "mapped", "ownership_mapping"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [dict(item) for item in nested if isinstance(item, Mapping)]
    return []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _domain(item: Mapping[str, Any]) -> str:
    raw = _text(
        item.get("owner_domain")
        or item.get("native_owner")
        or item.get("contract_owner")
        or item.get("contract_domain")
        or item.get("domain"),
        "runtime_authority",
    )
    raw = raw.replace("_contract", "").replace("runtime_authority", "runtime_authority")
    aliases = {
        "authority": "runtime_authority",
        "authority_owner": "runtime_authority",
        "step_executor": "step_executor",
        "taskrunner": "task_runner",
        "task_runner": "task_runner",
    }
    return aliases.get(raw, raw)


def _next_action(item: Mapping[str, Any], domain: str) -> str:
    raw = _text(item.get("next_action") or item.get("assertion_hint") or item.get("test_hint"))
    if raw:
        if "authority" in raw:
            return "extract_native_authority_contract_test"
        if "planning" in raw or "recovery" in raw:
            return "extract_planning_recovery_contract_test"
        return "bind_compatibility_path_to_native_owner_test"
    if domain == "runtime_authority":
        return "extract_native_authority_contract_test"
    if domain in {"step_executor", "task_runner"}:
        return "bind_compatibility_path_to_native_owner_test"
    return "extract_planning_recovery_contract_test"


def _assertions_for(domain: str, action: str) -> list[str]:
    if action == "extract_native_authority_contract_test":
        return [
            "explicit execution authority is present before runtime execution",
            "missing or invalid authority is blocked before side effects",
            "authority owner/source is preserved in result and evidence shape",
        ]
    if action == "extract_planning_recovery_contract_test":
        return [
            "fallback/recovery planning records contract evidence",
            "planner or recovery fallback does not bypass runtime authority",
            "contract evidence identifies native owner or blocker reason",
        ]
    if domain == "step_executor":
        return [
            "StepExecutor receives explicit authority from runtime/task layer",
            "StepExecutor blocks unowned execution before handler side effects",
            "step result and trace preserve runtime_mode and authority metadata",
        ]
    if domain == "task_runner":
        return [
            "TaskRunner propagates runtime_state through success and failure ticks",
            "TaskRunner preserves operator_session_id, failed_step, and recovery metadata",
            "TaskRunner returns stable status shape for finished/blocked/resumable paths",
        ]
    return [
        "compatibility path is bound to a native owner",
        "bridge path records contract evidence",
        "retirement prerequisite is explicit",
    ]


def _suggested_test_file(domain: str) -> str:
    return {
        "runtime_authority": "tests/test_native_runtime_authority_contracts.py",
        "step_executor": "tests/test_native_step_executor_contracts.py",
        "task_runner": "tests/test_native_task_runner_contracts.py",
        "scheduler": "tests/test_native_scheduler_contracts.py",
        "planner": "tests/test_native_planner_recovery_contracts.py",
    }.get(domain, "tests/test_native_runtime_contracts.py")


def _make_spec(index: int, item: Mapping[str, Any]) -> dict[str, Any]:
    domain = _domain(item)
    action = _next_action(item, domain)
    path = _text(item.get("path") or item.get("file") or item.get("source_path"), "unknown")
    line = item.get("line") or item.get("line_no") or item.get("source_line")
    owner = _text(item.get("native_owner") or item.get("owner") or domain, domain)
    return {
        "spec_id": f"native-contract-{index:03d}",
        "source_path": path,
        "source_line": line,
        "owner_domain": domain,
        "native_owner": owner,
        "next_action": action,
        "suggested_test_file": _suggested_test_file(domain),
        "assertions": _assertions_for(domain, action),
        "retirement_prerequisite": "native owner test must pass before retiring compatibility bridge",
        "source_item": dict(item),
    }


def _run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    return {
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    source = _read_json(STAGE5_MAPPING, [])
    summary5 = _read_json(STAGE5_SUMMARY, {})
    items = _as_list(source)

    if not items:
        # fallback from summary counts: generate placeholder specs so the stage remains useful
        counts = summary5.get("owner_domain_counts") or summary5.get("owner_domain") or {}
        if isinstance(counts, Mapping):
            generated = []
            for domain, count in counts.items():
                for _ in range(int(count)):
                    generated.append({"owner_domain": domain, "path": "summary_only", "source": "stage5_summary"})
            items = generated

    specs = [_make_spec(i + 1, item) for i, item in enumerate(items)]
    domain_counts = Counter(spec["owner_domain"] for spec in specs)
    action_counts = Counter(spec["next_action"] for spec in specs)
    test_file_counts = Counter(spec["suggested_test_file"] for spec in specs)

    zero_patch_residue = []
    for path in ROOT.glob("core/**/*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "ZERO_PATCH_" in text:
            zero_patch_residue.append(str(path.relative_to(ROOT)))

    verification = [_run(cmd) for cmd in VERIFY_COMMANDS]
    verification_passed = all(item["ok"] for item in verification)

    payload = {
        "schema": "zero.runtime.native_contract_test_specs.stage6.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(STAGE5_MAPPING),
        "items": specs,
    }
    summary = {
        "native_contract_test_specs": len(specs),
        "owner_domain_counts": dict(domain_counts),
        "next_action_counts": dict(action_counts),
        "suggested_test_file_counts": dict(test_file_counts),
        "zero_patch_residue_count": len(zero_patch_residue),
        "zero_patch_residue": zero_patch_residue,
        "verification_passed": verification_passed,
        "outputs": {
            "specs": str(OUT_JSON),
            "summary": str(OUT_SUMMARY),
            "report": str(OUT_REPORT),
        },
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Runtime Native Contract Test Specs Stage 6",
        "",
        "Inventory-only extraction of native runtime contract test specifications.",
        "This script does not modify runtime behavior.",
        "",
        "## Summary",
        "",
        f"- native contract test specs: {len(specs)}",
        f"- ZERO_PATCH residue: {len(zero_patch_residue)}",
        f"- verification passed: {verification_passed}",
        "",
        "## Owner domain counts",
        "",
    ]
    for key, value in domain_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Next action counts", ""]
    for key, value in action_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Suggested test files", ""]
    for key, value in test_file_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Verification", ""]
    for item in verification:
        status = "PASS" if item["ok"] else "FAIL"
        lines.append(f"### {status}: `{item['cmd']}`")
        lines.append("```text")
        lines.append((item["stdout"] or "").strip())
        if item["stderr"].strip():
            lines.append("--- stderr ---")
            lines.append(item["stderr"].strip())
        lines.append("```")
        lines.append("")
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"native contract test specs extracted: {len(specs)}")
    print(f"owner domain counts: {dict(domain_counts)}")
    print(f"next action counts: {dict(action_counts)}")
    print(f"ZERO_PATCH residue: {len(zero_patch_residue)}")
    print(f"report: {OUT_REPORT}")
    print(f"specs: {OUT_JSON}")
    print(f"summary: {OUT_SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
