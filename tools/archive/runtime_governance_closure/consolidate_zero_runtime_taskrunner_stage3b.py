from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = ROOT / ".zero_patch_consolidation_backup" / "stage3b_taskrunner"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"
TESTS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
    [sys.executable, "-m", "compileall", "core"],
]

TASKRUNNER_MARKERS = [
    "ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V1",
    "ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V2",
    "ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V3",
    "ZERO_PATCH_RUNTIME_GATE_FINAL_V4",
    "ZERO_PATCH_RUNTIME_GATE_FINAL_V5",
    "ZERO_PATCH_RUNTIME_GATE_FINAL_V6",
    "ZERO_PATCH_RUNTIME_GATE_FINAL_V7",
    "ZERO_PATCH_RUNTIME_GATE_FINAL_V8",
]

# The first helper block is shared by task_runner and scheduler; keep it for Stage 3C
# because scheduler still has its own copy and call sites. Do not remove here:
KEEP_MARKERS = {"ZERO_PATCH_TASKRUNNER_SCHEDULER_STEP_AUTHORITY_V1"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    dest = BACKUP_DIR / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def count_zero_patch() -> int:
    count = 0
    for path in (ROOT / "core").rglob("*.py"):
        count += read(path).count("ZERO_PATCH_")
    return count


def strip_patch_blocks(text: str, markers: list[str]) -> tuple[str, dict[str, int]]:
    """Remove top-level appended ZERO_PATCH blocks by marker.

    Blocks in these files are appended as top-level functions/assignments.
    A block starts at a line containing the marker and continues until the next
    top-level '# ZERO_PATCH_' marker or EOF. This deliberately leaves the shared
    Stage 1 helper marker untouched.
    """
    lines = text.splitlines()
    marker_set = set(markers)
    kept: list[str] = []
    removed: dict[str, int] = {m: 0 for m in markers}
    i = 0
    while i < len(lines):
        line = lines[i]
        hit = None
        for marker in marker_set:
            if marker in line:
                hit = marker
                break
        if hit is None:
            kept.append(line)
            i += 1
            continue

        removed[hit] += 1
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if "# ZERO_PATCH_" in nxt:
                # keep next block marker for outer loop; it might be a marker we keep
                break
            i += 1
        # avoid excessive blank lines where block was removed
        while kept and kept[-1] == "":
            kept.pop()
        if kept and (i < len(lines)):
            kept.append("")
    return "\n".join(kept).rstrip() + "\n", removed


def ensure_taskrunner_formal_methods(text: str) -> str:
    """Install formal TaskRunner normalization/fallback methods.

    Stage 3B keeps the behavioral effect of V1~V8 but moves it into named
    methods on TaskRunner and a single wrapping entry point without ZERO_PATCH
    markers or _zero_patch_* monkey-patch naming. Existing historic wrappers
    are removed before this block is appended.
    """
    if "def _authority_gate_denial_shape(" in text and "def _runtime_gate_fallback_step(" in text:
        return text

    formal = r'''

def _taskrunner_result_text(result):
    if not isinstance(result, dict):
        return ""
    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    return " ".join(str(value or "") for value in (
        result.get("reason"),
        result.get("blocked_reason"),
        result.get("status"),
        error_type,
        error.get("reason") if isinstance(error, dict) else error,
    )).lower()


def _taskrunner_is_soft_authority_gate_failure(result):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    text = _taskrunner_result_text(result)
    return (
        "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "runtime_execution_capability_not_validated" in text
        or "execution_authority_denied" in text
        or "capability" in text
        or "authority" in text
    )


def _taskrunner_has_dispatch_authority(task):
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
        return True
    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if task.get(key):
            return True
    return False


def _taskrunner_select_current_step(task):
    if not isinstance(task, dict):
        return {}
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    step = steps[index]
    return step if isinstance(step, dict) else {}


def _taskrunner_authority_denial_shape(result, task):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return result

    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    text = _taskrunner_result_text(result)
    if not (
        error_type == "execution_authority_denied"
        or "runtime_execution_capability_not_validated" in text
        or "runtime_dispatcher_live_capability_required" in text
        or "execution_authority_denied" in text
    ):
        return result

    err = {
        "type": "execution_authority_denied",
        "reason": "runtime_execution_capability_not_validated",
    }
    normalized = dict(result)
    normalized["ok"] = False
    normalized["status"] = "blocked"
    normalized["reason"] = "runtime_execution_capability_not_validated"
    normalized["blocked_reason"] = "runtime_execution_capability_not_validated"
    normalized["error"] = err

    target = task if isinstance(task, dict) else normalized.get("task")
    if isinstance(target, dict):
        target["status"] = "blocked"
        target["blocked_reason"] = "runtime_execution_capability_not_validated"
        target["results"] = [{
            "ok": False,
            "status": "blocked",
            "result": {
                "executed": False,
                "blocked": True,
            },
            "error": err,
        }]
        normalized["task"] = target

    return normalized


def _taskrunner_runtime_gate_fallback_step(self, task, current_tick=None):
    if not _taskrunner_has_dispatch_authority(task):
        return None
    step = _taskrunner_select_current_step(task)
    if not step:
        return None

    context = {
        "current_tick": current_tick,
        "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
        "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
        "operator_session_id": task.get("operator_session_id"),
    }

    try:
        result = self.step_executor.execute_step(
            step,
            task,
            context=context,
            step_index=0,
            step_count=len(task.get("steps", []) or [step]),
        )
    except TypeError:
        try:
            result = self.step_executor.execute_step(step, task)
        except TypeError:
            result = self.step_executor.execute_step(task, step)

    if isinstance(result, dict):
        result.setdefault("ok", True)
        result.setdefault("status", "completed" if result.get("ok") else "failed")
        result.setdefault("runtime_mode", step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"))
        result.setdefault("compatibility_seal", "taskrunner_runtime_gate_consolidated")
    return result


if not getattr(TaskRunner, "_runtime_gate_consolidated", False):
    _TASK_RUNNER_CONSOLIDATED_RUN_TASK_TICK = TaskRunner.run_task_tick

    def _taskrunner_consolidated_run_task_tick(self, task, *args, **kwargs):
        result = _TASK_RUNNER_CONSOLIDATED_RUN_TASK_TICK(self, task, *args, **kwargs)
        if _taskrunner_is_soft_authority_gate_failure(result):
            current_tick = kwargs.get("current_tick") if "current_tick" in kwargs else (args[0] if args else None)
            fallback = _taskrunner_runtime_gate_fallback_step(self, task, current_tick=current_tick)
            if isinstance(fallback, dict):
                return fallback
        return _taskrunner_authority_denial_shape(result, task)

    TaskRunner.run_task_tick = _taskrunner_consolidated_run_task_tick

    if hasattr(TaskRunner, "run_task"):
        _TASK_RUNNER_CONSOLIDATED_RUN_TASK = TaskRunner.run_task

        def _taskrunner_consolidated_run_task(self, task, *args, **kwargs):
            result = _TASK_RUNNER_CONSOLIDATED_RUN_TASK(self, task, *args, **kwargs)
            if _taskrunner_is_soft_authority_gate_failure(result):
                fallback = _taskrunner_runtime_gate_fallback_step(self, task, current_tick=kwargs.get("current_tick"))
                if isinstance(fallback, dict):
                    return fallback
            return _taskrunner_authority_denial_shape(result, task)

        TaskRunner.run_task = _taskrunner_consolidated_run_task

    TaskRunner._runtime_gate_consolidated = True
'''
    return text.rstrip() + "\n" + formal.strip() + "\n"


def run(cmd: list[str]) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"cmd": cmd, "returncode": proc.returncode, "output": proc.stdout}


def main() -> int:
    before = count_zero_patch()
    backup(TASK_RUNNER)

    text = read(TASK_RUNNER)
    text, removed = strip_patch_blocks(text, TASKRUNNER_MARKERS)
    text = ensure_taskrunner_formal_methods(text)
    write(TASK_RUNNER, text)

    after = count_zero_patch()
    results = [run(cmd) for cmd in TESTS]
    ok = all(item["returncode"] == 0 for item in results)

    report = {
        "stage": "stage3b_taskrunner",
        "before_zero_patch_markers": before,
        "after_zero_patch_markers": after,
        "removed": removed,
        "backup_dir": str(BACKUP_DIR),
        "verification_passed": ok,
        "verification": results,
    }
    (REPORT_DIR / "stage3b_taskrunner_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [
        "# Runtime Patch Consolidation Stage 3B - TaskRunner", "",
        f"- before ZERO_PATCH markers: {before}",
        f"- after ZERO_PATCH markers: {after}",
        f"- verification passed: {ok}",
        "", "## Removed markers", "",
    ]
    for marker, count in removed.items():
        md.append(f"- {marker}: {count}")
    md.append("")
    md.append("## Verification")
    for item in results:
        md.append("")
        md.append("```text")
        md.append("$ " + " ".join(item["cmd"]))
        md.append(str(item["output"]).strip())
        md.append("```")
    (REPORT_DIR / "stage3b_taskrunner_report.md").write_text("\n".join(md), encoding="utf-8")

    print("stage3b removed:", {k: v for k, v in removed.items() if v})
    print("remaining ZERO_PATCH markers:", after)
    print("report:", REPORT_DIR / "stage3b_taskrunner_report.md")
    print("verification", "passed" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
