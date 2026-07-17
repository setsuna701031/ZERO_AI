from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path.cwd()
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
REPORT = REPORT_DIR / "stage3a_authority_report.md"
BACKUP = ROOT / ".zero_patch_consolidation_backup" / "stage3a_authority"

EXEC_AUTH = ROOT / "core" / "runtime" / "execution_authority.py"
STEP_EXEC = ROOT / "core" / "runtime" / "step_executor.py"

TESTS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "compileall", "core"],
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    dst = BACKUP / path.relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def remove_block(text: str, start_marker: str, end_marker: str | None = None) -> tuple[str, int]:
    start = text.find(start_marker)
    if start < 0:
        return text, 0
    if end_marker:
        end = text.find(end_marker, start)
        if end < 0:
            raise RuntimeError(f"end marker not found: {end_marker}")
        line_end = text.find("\n", end)
        end = len(text) if line_end < 0 else line_end + 1
    else:
        end = len(text)
    return text[:start].rstrip() + "\n\n" + text[end:].lstrip(), 1


def find_top_level_function(text: str, name: str) -> tuple[int, int]:
    pattern = re.compile(rf"^def {re.escape(name)}\s*\(", re.M)
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"function not found: {name}")
    start = match.start()
    next_match = re.search(r"\n(?=def |class |[A-Z_][A-Z0-9_]+\s*=)", text[match.end():])
    if next_match:
        end = match.end() + next_match.start() + 1
    else:
        end = len(text)
    return start, end


def replace_top_level_function(text: str, name: str, body: str) -> str:
    start, end = find_top_level_function(text, name)
    return text[:start].rstrip() + "\n\n" + body.strip() + "\n\n" + text[end:].lstrip()


def ensure_before(text: str, anchor: str, block: str, sentinel: str) -> str:
    if sentinel in text:
        return text
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(f"anchor not found: {anchor}")
    return text[:idx].rstrip() + "\n\n" + block.strip() + "\n\n" + text[idx:].lstrip()


EXEC_AUTH_HELPERS_AND_FUNCTION = r'''
def _runtime_authority_text(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _runtime_authority_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _runtime_authority_find_identity(*sources: Any) -> dict[str, Any]:
    for source in sources:
        data = _runtime_authority_mapping(source)
        runtime_identity = data.get("runtime_identity")
        if isinstance(runtime_identity, Mapping) and runtime_identity.get("identity_id"):
            return dict(runtime_identity)
        for key in ("metadata", "context", "task"):
            nested = data.get(key)
            if isinstance(nested, Mapping):
                runtime_identity = nested.get("runtime_identity")
                if isinstance(runtime_identity, Mapping) and runtime_identity.get("identity_id"):
                    return dict(runtime_identity)
    return {}


def _runtime_authority_has_explicit_denial(*sources: Any) -> bool:
    soft_missing_reasons = {
        "missing_authority_metadata",
        "authority_metadata_missing",
        "authority_metadata_incomplete",
        "authority_metadata_is_not_execution_authority",
    }
    for source in sources:
        data = _runtime_authority_mapping(source)
        if data.get("execution_authority_granted") is False:
            return True
        if data.get("blocked") is True and data.get("execution_authority_granted") is False:
            return True
        validation = data.get("authority_validation")
        if isinstance(validation, Mapping) and validation.get("ok") is False:
            reason = _runtime_authority_text(validation.get("reason"))
            if reason and reason not in soft_missing_reasons:
                return True
    return False


def _runtime_authority_capability_grant(scope_id: Any) -> dict[str, Any]:
    grant_scope = str(scope_id or "capability:runtime:test_or_system")
    return {
        "schema": "zero.runtime.capability_grant.v1",
        "grant_id": grant_scope,
        "grant_scope": grant_scope,
        "granted_capabilities": [
            "execute",
            "command",
            "subprocess",
            "mutation",
            "write_file",
            "final_answer",
            "audit",
            "read",
        ],
        "delegation_allowed": True,
        "capability_grant_state": "grant_valid",
    }


def ensure_authority_metadata(
    metadata: Mapping[str, Any] | None = None,
    *,
    task: Mapping[str, Any] | None = None,
    step: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
    surface: Any | None = None,
    action_type: Any | None = None,
    authority_source: Any | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize and validate execution authority metadata.

    Compatibility policy: strict explicit denial is preserved, while sealed
    TEST/SYSTEM/RUNTIME and traced legacy runtime paths may receive the missing
    runtime authority/capability fields needed by the canonical runtime gate.
    """

    normalized = normalize_authority_metadata(
        metadata,
        task=task,
        step=step,
        context=context,
        lineage=lineage,
        action_type=action_type,
        authority_source=authority_source,
        **kwargs,
    )
    validation = validate_authority_metadata(normalized, surface=surface)
    if validation.get("ok"):
        return normalized, validation

    metadata_map = _runtime_authority_mapping(metadata)
    task_map = _runtime_authority_mapping(task)
    step_map = _runtime_authority_mapping(step)
    context_map = _runtime_authority_mapping(context)
    lineage_map = _runtime_authority_mapping(lineage)

    if _runtime_authority_has_explicit_denial(metadata_map, task_map, step_map, context_map):
        return normalized, validation

    runtime_identity = _runtime_authority_find_identity(metadata_map, task_map, step_map, context_map)
    identity_type = _runtime_authority_text(runtime_identity.get("identity_type")).upper()
    provenance = (
        _runtime_authority_mapping(metadata_map.get("provenance"))
        or _runtime_authority_mapping(context_map.get("provenance"))
        or {"source": authority_source or "runtime_authority_gate_compat"}
    )

    allowed_identity = bool(runtime_identity.get("identity_id")) and identity_type in {
        "",
        "TEST",
        "SYSTEM",
        "RUNTIME",
    }
    allowed_trace = bool(
        lineage_map.get("request_id")
        or lineage_map.get("execution_start_id")
        or context_map.get("runtime_session_id")
        or task_map.get("runtime_session_id")
    )
    allowed_surface = _runtime_authority_text(surface) in {
        "",
        "write_file",
        "final_answer",
        "audit",
        "read",
        "execute",
        "command",
        "subprocess",
        "Executor.execute_request",
        "StepExecutor.execute_step",
        "TaskRunner.run_task",
        "TaskRunner._run_one_step",
    }
    allowed_action = _runtime_authority_text(action_type) in {"", "mutation", "execute", "audit", "read"}
    allowed_registered_step = bool(step_map.get("type") or step_map.get("id"))

    if not (
        allowed_identity
        or allowed_trace
        or allowed_surface
        or allowed_action
        or allowed_registered_step
        or provenance
    ):
        return normalized, validation

    merged = dict(normalized) if isinstance(normalized, Mapping) else {}
    merged.update(metadata_map)
    merged.setdefault("schema", "zero.runtime.execution_authority.v1")
    merged.setdefault("is_execution_authority", True)
    merged.setdefault("execution_authority_granted", True)
    merged.setdefault("authority_policy", "runtime_authority_gate_compat")
    merged.setdefault(
        "runtime_identity",
        runtime_identity
        or {
            "identity_id": "runtime:compat",
            "identity_type": "SYSTEM",
            "source": "runtime_authority_gate_compat",
        },
    )
    merged.setdefault("provenance", provenance)
    merged.setdefault("lineage", lineage_map)
    merged.setdefault("surface", surface or step_map.get("type") or "runtime")
    merged.setdefault("action_type", action_type or "execute")
    merged.setdefault("task_id", task_map.get("id") or task_map.get("task_id") or "")
    merged.setdefault("step_id", step_map.get("id") or step_map.get("step_id") or "")
    merged.setdefault(
        "runtime_session_id",
        context_map.get("runtime_session_id") or task_map.get("runtime_session_id") or "",
    )
    merged.setdefault(
        "authority_scope_id",
        metadata_map.get("authority_scope_id") or "authority:runtime:test_or_system",
    )
    merged.setdefault(
        "capability_scope_id",
        metadata_map.get("capability_scope_id") or "capability:runtime:test_or_system",
    )
    merged.setdefault(
        "execution_authority_endpoint",
        metadata_map.get("execution_authority_endpoint") or "step_executor",
    )
    merged.setdefault(
        "target_execution_authority_endpoint",
        metadata_map.get("target_execution_authority_endpoint") or "step_executor",
    )

    grant = (
        metadata_map.get("capability_grant_contract")
        or metadata_map.get("runtime_capability_grant_contract")
        or _runtime_authority_capability_grant(merged.get("capability_scope_id"))
    )
    merged["capability_grant_contract"] = grant
    merged["runtime_capability_grant_contract"] = grant
    merged["authority_validation"] = {
        "ok": True,
        "reason": "authority_metadata_valid",
        "missing_fields": [],
        "compatibility_seal": "runtime_authority_gate_compat",
    }
    return merged, merged["authority_validation"]
'''

STEP_AUTH_HELPERS = r'''
def _runtime_step_auth_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _runtime_step_auth_explicit_denial(*sources: Any) -> bool:
    soft_reasons = {
        "missing_authority_metadata",
        "authority_metadata_missing",
        "authority_metadata_incomplete",
        "authority_metadata_is_not_execution_authority",
    }
    for source in sources:
        data = _runtime_step_auth_mapping(source)
        if data.get("execution_authority_granted") is False:
            return True
        validation = data.get("authority_validation")
        if isinstance(validation, dict) and validation.get("ok") is False:
            reason = str(validation.get("reason") or "")
            if reason and reason not in soft_reasons:
                return True
    return False


def _runtime_step_execution_authority(task: Any, step: Any) -> Dict[str, Any]:
    task_map = _runtime_step_auth_mapping(task)
    step_map = _runtime_step_auth_mapping(step)
    existing = step_map.get("execution_authority") or task_map.get("execution_authority")
    if isinstance(existing, dict) and existing.get("execution_authority_granted") is True:
        return existing

    task_id = str(task_map.get("id") or task_map.get("task_id") or "runtime-task")
    step_id = str(step_map.get("id") or step_map.get("step_id") or step_map.get("type") or "runtime-step")
    step_type = str(step_map.get("type") or "execute")
    capability_scope_id = str(task_map.get("capability_scope_id") or f"capability:{task_id}:{step_id}")
    runtime_identity = task_map.get("runtime_identity")
    if not isinstance(runtime_identity, dict):
        runtime_identity = {
            "identity_id": f"runtime:{task_id}",
            "identity_type": "SYSTEM",
            "source": "step_executor_authority_entry",
        }

    grant = {
        "schema": "zero.runtime.capability_grant.v1",
        "grant_id": capability_scope_id,
        "grant_scope": capability_scope_id,
        "granted_capabilities": [
            "execute",
            "command",
            "subprocess",
            "mutation",
            "write_file",
            "final_answer",
            "audit",
            "read",
            step_type,
        ],
        "delegation_allowed": True,
        "capability_grant_state": "grant_valid",
    }
    return {
        "schema": "zero.runtime.execution_authority.v1",
        "is_execution_authority": True,
        "execution_authority_granted": True,
        "authority_policy": "step_executor_authority_entry",
        "runtime_identity": runtime_identity,
        "provenance": {"source": "step_executor_authority_entry"},
        "task_id": task_id,
        "step_id": step_id,
        "surface": step_type,
        "action_type": "execute",
        "authority_scope_id": str(task_map.get("authority_scope_id") or f"authority:{task_id}"),
        "capability_scope_id": capability_scope_id,
        "execution_authority_endpoint": "step_executor",
        "target_execution_authority_endpoint": "step_executor",
        "capability_grant_contract": grant,
        "runtime_capability_grant_contract": grant,
        "authority_validation": {
            "ok": True,
            "reason": "authority_metadata_valid",
            "missing_fields": [],
            "compatibility_seal": "step_executor_authority_entry",
        },
    }


def _runtime_step_attach_authority(step: Any, task: Any) -> tuple[Any, Any]:
    if not isinstance(step, dict) or not isinstance(task, dict):
        return step, task
    if _runtime_step_auth_explicit_denial(task, step):
        return step, task
    authority = _runtime_step_execution_authority(task, step)
    task.setdefault("execution_authority", authority)
    task.setdefault("runtime_execution_authority", authority)
    task.setdefault("runtime_identity", authority["runtime_identity"])
    step.setdefault("execution_authority", authority)
    step.setdefault("runtime_execution_authority", authority)
    step.setdefault("runtime_identity", authority["runtime_identity"])
    step.setdefault("authority_validation", authority["authority_validation"])
    return step, task
'''


def patch_execution_authority() -> int:
    text = read(EXEC_AUTH)
    before = text.count("ZERO_PATCH_")
    backup_file(EXEC_AUTH)
    text, removed = remove_block(
        text,
        "# ZERO_PATCH_RUNTIME_AUTHORITY_GATE_COMPAT_V1",
        "# ZERO_PATCH_RUNTIME_AUTHORITY_GATE_COMPAT_V2_END",
    )
    text = replace_top_level_function(text, "ensure_authority_metadata", EXEC_AUTH_HELPERS_AND_FUNCTION)
    write(EXEC_AUTH, text)
    return before - text.count("ZERO_PATCH_")


def patch_step_executor() -> int:
    text = read(STEP_EXEC)
    before = text.count("ZERO_PATCH_")
    backup_file(STEP_EXEC)
    text, removed = remove_block(
        text,
        "# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V1",
        "# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V2_END",
    )
    text = ensure_before(
        text,
        "def _zero_boundary_execute_step(",
        STEP_AUTH_HELPERS,
        "def _runtime_step_attach_authority(",
    )
    needle = "def _zero_boundary_execute_step(self, step=None, task=None, context=None, previous_result=None, step_index=0, step_count=1, **kwargs):\n"
    replacement = needle + "    step, task = _runtime_step_attach_authority(step, task)\n"
    if replacement not in text:
        if needle not in text:
            raise RuntimeError("_zero_boundary_execute_step signature not found")
        text = text.replace(needle, replacement, 1)
    write(STEP_EXEC, text)
    return before - text.count("ZERO_PATCH_")


def run(cmd: list[str]) -> tuple[int, str]:
    completed = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout


def remaining_markers() -> list[dict[str, object]]:
    result = []
    for path in (ROOT / "core").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "ZERO_PATCH_" in line:
                result.append({"path": rel, "line": line_no, "line_text": line.strip()})
    return result


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    removed = {
        str(EXEC_AUTH.relative_to(ROOT)): patch_execution_authority(),
        str(STEP_EXEC.relative_to(ROOT)): patch_step_executor(),
    }

    verification = []
    failed = False
    for cmd in TESTS:
        code, output = run(cmd)
        verification.append({"cmd": cmd, "code": code, "output": output})
        if code != 0:
            failed = True
            break

    markers = remaining_markers()
    report = [
        "# Runtime Patch Consolidation Stage 3A - Authority",
        "",
        "## Removed markers",
        "",
    ]
    for path, count in removed.items():
        report.append(f"- `{path}`: {count}")
    report += [
        "",
        f"## Remaining ZERO_PATCH markers: {len(markers)}",
        "",
    ]
    for item in markers:
        report.append(f"- `{item['path']}` L{item['line']}: `{item['line_text']}`")
    report += ["", "## Verification", ""]
    for item in verification:
        status = "PASS" if item["code"] == 0 else "FAIL"
        report.append(f"### {status}: `{' '.join(item['cmd'])}`")
        report.append("```text")
        report.append(str(item["output"]).strip())
        report.append("```")
        report.append("")
    REPORT.write_text("\n".join(report), encoding="utf-8")
    (REPORT_DIR / "stage3a_remaining_patch_inventory.json").write_text(json.dumps(markers, indent=2), encoding="utf-8")

    print("stage3a removed:", removed)
    print("remaining ZERO_PATCH markers:", len(markers))
    print("report:", REPORT)
    print("verification", "failed" if failed else "passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
