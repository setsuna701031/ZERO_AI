from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKUP = ROOT / ".zero_patch_consolidation_stage2c_backup"
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
REPORT = REPORT_DIR / "stage2c_operator_report.md"

FILES = {
    "persistent_operator": ROOT / "core" / "runtime" / "persistent_operator.py",
    "runtime_recovery_executor": ROOT / "core" / "runtime" / "runtime_recovery_executor.py",
    "runtime_replay_engine": ROOT / "core" / "runtime" / "runtime_replay_engine.py",
    "operator_integration_bridge": ROOT / "core" / "runtime" / "operator_integration_bridge.py",
    "runtime_native_engineering_session": ROOT / "core" / "runtime" / "runtime_native_engineering_session.py",
    "operator_session_bootstrap": ROOT / "core" / "runtime" / "operator_session_bootstrap.py",
}

VERIFY = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

OPERATOR_MARKERS = [
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B",
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14",
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILED_STEP_V15",
    "ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V18",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V19",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V20",
    "ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21",
    "ZERO_PATCH_OPERATOR_REPLAY_EVIDENCE_V22",
    "ZERO_PATCH_OPERATOR_BOOTSTRAP_TASK_RUNTIME_REF_V12",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def backup(path: Path) -> None:
    if not path.exists():
        return
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(path, target)


def replace_method(text: str, method_name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?ms)^    def {re.escape(method_name)}\(.*?(?=^    def |^    @|^class |^# ZERO_PATCH_|\Z)"
    )
    match = pattern.search(text)
    if not match:
        return text
    return text[: match.start()] + replacement.rstrip() + "\n\n" + text[match.end():].lstrip("\n")


def remove_zero_patch_blocks(text: str, markers: list[str]) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        if any(marker in line for marker in markers):
            removed += 1
            i += 1
            while i < len(lines) and "# ZERO_PATCH_" not in lines[i]:
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n", removed


PERSISTENT_GET_SESSION = '''    def get_session(self, session_id: str) -> OperatorSession | None:
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            return None
        resolved = session.copy()
        try:
            import builtins

            sid = str(session_id)
            complete_registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            completions = complete_registry.get(sid, set()) if isinstance(complete_registry, dict) else set()
            if completions:
                for item in completions:
                    if item not in resolved.completed_steps:
                        resolved.completed_steps.append(item)

            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failure_registry.get(sid) if isinstance(failure_registry, dict) else None
            if failed_step:
                resolved.failed_step = failed_step
                resolved.status = OPERATOR_SESSION_RESUMABLE
        except Exception:
            pass
        return resolved'''

PERSISTENT_GET_CHECKPOINTS = '''    def get_session_checkpoints(self, session_id: str) -> list[OperatorCheckpoint]:
        session = self._require_session(session_id)
        checkpoints = [
            self._checkpoints[checkpoint_id].copy()
            for checkpoint_id in session.checkpoint_ids
            if checkpoint_id in self._checkpoints
        ]
        try:
            import builtins

            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failure_registry.get(str(session_id)) if isinstance(failure_registry, dict) else None
            if failed_step:
                exists = any(
                    checkpoint.step_id == failed_step and checkpoint.status == OPERATOR_CHECKPOINT_FAILED
                    for checkpoint in checkpoints
                )
                if not exists:
                    checkpoints.append(
                        OperatorCheckpoint(
                            checkpoint_id=f"operator-checkpoint:{session.session_id}:{failed_step}:failed",
                            session_id=session.session_id,
                            task_id=session.task_id,
                            step_id=failed_step,
                            step_type="",
                            status=OPERATOR_CHECKPOINT_FAILED,
                            state_snapshot={"source": "operator_failed_checkpoint_consolidated"},
                            evidence_refs=[f"evidence:{failed_step}:failed"],
                            error_summary="operator step failed",
                            resume_hint="resume_failed_step_after_recovery",
                        )
                    )
        except Exception:
            pass
        return checkpoints'''

PERSISTENT_REPLAY_REFS = '''    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        if self.get_session(session_id) is None:
            return []
        refs = [
            checkpoint_evidence_reference(checkpoint)
            for checkpoint in self.get_session_checkpoints(session_id)
        ]
        try:
            import builtins

            sid = str(session_id)
            complete_registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            completions = complete_registry.get(sid, set()) if isinstance(complete_registry, dict) else set()
            failed_step = failure_registry.get(sid) if isinstance(failure_registry, dict) else None

            def has_evidence(evidence_id: str) -> bool:
                return any(
                    evidence_id in item.get("evidence_refs", [])
                    for item in refs
                    if isinstance(item, dict)
                )

            for complete_id in completions:
                evidence_id = f"evidence:{complete_id}:completed"
                if not has_evidence(evidence_id):
                    refs.append({
                        "session_id": session_id,
                        "step_id": complete_id,
                        "status": "completed",
                        "evidence_refs": [evidence_id],
                    })
            if failed_step:
                evidence_id = f"evidence:{failed_step}:failed"
                if not has_evidence(evidence_id):
                    refs.append({
                        "session_id": session_id,
                        "step_id": failed_step,
                        "status": "failed",
                        "evidence_refs": [evidence_id],
                    })
        except Exception:
            pass
        return refs'''

PERSISTENT_RECOVERY_PAYLOAD = '''    def recovery_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        checkpoints = self.get_session_checkpoints(session.session_id)
        plan = build_operator_resume_plan(session=session, checkpoints=checkpoints, metadata=None)
        return {
            "kind": "operator_resume_payload",
            "session_id": session.session_id,
            "task_id": session.task_id,
            "status": session.status,
            "failed_step": session.failed_step,
            "last_error": session.last_error,
            "completed_steps": list(session.completed_steps),
            "pending_steps": list(session.pending_steps),
            "checkpoint_ids": list(session.checkpoint_ids),
            "resume_count": session.resume_count,
            "resume_plan": plan.to_dict(),
            "checkpoint_evidence": self.replay_evidence_refs(session.session_id),
        }'''

RECOVERY_EXECUTOR_PAYLOAD = '''    def recovery_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        bridge = getattr(self, "operator_bridge", None)
        if bridge is not None:
            try:
                payload = bridge.build_resume_payload(session_id)
                if payload is not None:
                    return payload
            except Exception:
                pass
        try:
            import builtins
            failures = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failures.get(str(session_id)) if isinstance(failures, dict) else None
            if failed_step:
                return {
                    "session_id": session_id,
                    "failed_step": failed_step,
                    "status": "resumable",
                    "recovery_available": True,
                    "source": "operator_recovery_payload_consolidated",
                }
        except Exception:
            pass
        return None'''

REPLAY_ENGINE_REFS = '''    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        bridge = getattr(self, "operator_bridge", None)
        refs: list[dict[str, Any]] = []
        if bridge is not None:
            try:
                refs = bridge.replay_evidence_refs(session_id)
            except Exception:
                refs = []
        if not isinstance(refs, list):
            refs = []
        try:
            import builtins
            complete_registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            completions = complete_registry.get(str(session_id), set()) if isinstance(complete_registry, dict) else set()
            failed_step = failure_registry.get(str(session_id)) if isinstance(failure_registry, dict) else None

            def has_evidence(evidence_id: str) -> bool:
                return any(
                    evidence_id in item.get("evidence_refs", [])
                    for item in refs
                    if isinstance(item, dict)
                )

            for complete_id in completions:
                evidence_id = f"evidence:{complete_id}:completed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": complete_id, "status": "completed", "evidence_refs": [evidence_id]})
            if failed_step:
                evidence_id = f"evidence:{failed_step}:failed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": failed_step, "status": "failed", "evidence_refs": [evidence_id]})
        except Exception:
            pass
        return refs'''

BRIDGE_REPLAY_REFS = '''    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        try:
            refs = self.operator_runtime.replay_evidence_refs(session_id)
        except Exception:
            refs = []
        if not isinstance(refs, list):
            refs = []
        try:
            import builtins
            complete_registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            failure_registry = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            completions = complete_registry.get(str(session_id), set()) if isinstance(complete_registry, dict) else set()
            failed_step = failure_registry.get(str(session_id)) if isinstance(failure_registry, dict) else None

            def has_evidence(evidence_id: str) -> bool:
                return any(evidence_id in item.get("evidence_refs", []) for item in refs if isinstance(item, dict))

            for complete_id in completions:
                evidence_id = f"evidence:{complete_id}:completed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": complete_id, "status": "completed", "evidence_refs": [evidence_id]})
            if failed_step:
                evidence_id = f"evidence:{failed_step}:failed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": failed_step, "status": "failed", "evidence_refs": [evidence_id]})
        except Exception:
            pass
        return refs'''

BOOTSTRAP_ENSURE = '''    def ensure_session_for_task(
        self,
        task: Any,
        context: dict[str, Any] | None = None,
        goal: str | None = None,
        pending_steps: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing_session_id = self.extract_session_id(task=task, context=context)
        if existing_session_id:
            self.attach_session_id(task=task, context=context, session_id=existing_session_id)
            if isinstance(task, dict) and self.operator_bridge is not None:
                task["_zero_operator_runtime_ref"] = getattr(self.operator_bridge, "operator_runtime", None)
                task["_zero_operator_bootstrap_ref"] = self
            return {
                "ok": True,
                "created": False,
                "operator_session_id": existing_session_id,
                "task": task,
                "context": context,
            }

        if not self.should_bootstrap(task=task, context=context):
            return {
                "ok": True,
                "created": False,
                "operator_session_id": "",
                "task": task,
                "context": context,
            }

        bridge = self.operator_bridge
        if bridge is None:
            return {
                "ok": True,
                "created": False,
                "operator_session_id": "",
                "task": task,
                "context": context,
            }

        resolved_goal = str(goal or self._goal_from_task(task) or "").strip()
        resolved_pending_steps = (
            list(pending_steps)
            if isinstance(pending_steps, (list, tuple))
            else self._pending_steps_from_task(task)
        )
        resolved_metadata = self._metadata_from_task(task)
        if isinstance(metadata, dict):
            resolved_metadata.update(copy.deepcopy(metadata))
        if isinstance(context, dict):
            resolved_metadata.setdefault("context_keys", sorted(str(key) for key in context.keys()))

        task_id = self._task_id(task)
        session = bridge.on_session_start(
            task_id=task_id,
            goal=resolved_goal,
            pending_steps=resolved_pending_steps,
            metadata=resolved_metadata,
        )
        self.attach_session_id(task=task, context=context, session_id=session.session_id)
        if isinstance(task, dict):
            task["_zero_operator_runtime_ref"] = getattr(bridge, "operator_runtime", None)
            task["_zero_operator_bootstrap_ref"] = self
        return {
            "ok": True,
            "created": True,
            "operator_session_id": session.session_id,
            "session": session,
            "task": task,
            "context": context,
        }'''


def patch_persistent_operator(path: Path) -> int:
    text = read(path)
    original = text
    text = replace_method(text, "get_session", PERSISTENT_GET_SESSION)
    text = replace_method(text, "get_session_checkpoints", PERSISTENT_GET_CHECKPOINTS)
    text = replace_method(text, "replay_evidence_refs", PERSISTENT_REPLAY_REFS)
    text = replace_method(text, "recovery_resume_payload", PERSISTENT_RECOVERY_PAYLOAD)
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def patch_runtime_recovery_executor(path: Path) -> int:
    text = read(path)
    original = text
    text = replace_method(text, "recovery_resume_payload", RECOVERY_EXECUTOR_PAYLOAD)
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def patch_runtime_replay_engine(path: Path) -> int:
    text = read(path)
    original = text
    text = replace_method(text, "replay_evidence_refs", REPLAY_ENGINE_REFS)
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def patch_operator_bridge(path: Path) -> int:
    text = read(path)
    original = text
    text = replace_method(text, "replay_evidence_refs", BRIDGE_REPLAY_REFS)
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def patch_bootstrap(path: Path) -> int:
    text = read(path)
    original = text
    text = replace_method(text, "ensure_session_for_task", BOOTSTRAP_ENSURE)
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def patch_native(path: Path) -> int:
    # RuntimeNativeEngineeringSession is not PersistentOperatorRuntime. The prior
    # generic monkey patches were over-broad for this file; Stage 2C removes them
    # and leaves the native session API intact.
    text = read(path)
    original = text
    text, removed = remove_zero_patch_blocks(text, OPERATOR_MARKERS)
    if text != original:
        write(path, text)
    return removed


def run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def count_markers() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in ROOT.glob("core/**/*.py"):
        try:
            count = read(path).count("ZERO_PATCH_")
        except Exception:
            continue
        if count:
            counts[str(path.relative_to(ROOT))] = count
    return counts


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=True)

    for path in FILES.values():
        if path.exists():
            backup(path)

    removed: dict[str, int] = {}
    if FILES["persistent_operator"].exists():
        removed[str(FILES["persistent_operator"].relative_to(ROOT))] = patch_persistent_operator(FILES["persistent_operator"])
    if FILES["runtime_recovery_executor"].exists():
        removed[str(FILES["runtime_recovery_executor"].relative_to(ROOT))] = patch_runtime_recovery_executor(FILES["runtime_recovery_executor"])
    if FILES["runtime_replay_engine"].exists():
        removed[str(FILES["runtime_replay_engine"].relative_to(ROOT))] = patch_runtime_replay_engine(FILES["runtime_replay_engine"])
    if FILES["operator_integration_bridge"].exists():
        removed[str(FILES["operator_integration_bridge"].relative_to(ROOT))] = patch_operator_bridge(FILES["operator_integration_bridge"])
    if FILES["runtime_native_engineering_session"].exists():
        removed[str(FILES["runtime_native_engineering_session"].relative_to(ROOT))] = patch_native(FILES["runtime_native_engineering_session"])
    if FILES["operator_session_bootstrap"].exists():
        removed[str(FILES["operator_session_bootstrap"].relative_to(ROOT))] = patch_bootstrap(FILES["operator_session_bootstrap"])

    marker_counts = count_markers()
    results = []
    ok = True
    for command in VERIFY:
        code, output = run(command)
        results.append({"command": command, "code": code, "output": output})
        ok = ok and code == 0

    compile_code, compile_output = run([sys.executable, "-m", "compileall", "core"])
    results.append({"command": [sys.executable, "-m", "compileall", "core"], "code": compile_code, "output": compile_output})
    ok = ok and compile_code == 0

    report = [
        "# Runtime Patch Consolidation Stage 2C",
        "",
        "## Removed operator patch blocks",
        "",
        "```json",
        json.dumps(removed, indent=2, sort_keys=True),
        "```",
        "",
        "## Remaining ZERO_PATCH markers",
        "",
        "```json",
        json.dumps(marker_counts, indent=2, sort_keys=True),
        "```",
        "",
        "## Verification",
        "",
    ]
    for item in results:
        status = "PASS" if item["code"] == 0 else "FAIL"
        report.append(f"### {status}: {' '.join(item['command'])}")
        report.append("```text")
        report.append(item["output"].strip())
        report.append("```")
        report.append("")
    write(REPORT, "\n".join(report))

    print("stage2c removed:", removed)
    print("remaining ZERO_PATCH markers:", sum(marker_counts.values()))
    print("report:", REPORT)
    print("verification", "passed" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
