from __future__ import annotations

"""ZERO runtime patch consolidation stage 2: operator runtime readback.

This script removes the operator/recovery/replay ZERO_PATCH monkey patches and
folds their behavior into the primary class methods. It deliberately does not
consolidate Scheduler/TaskRunner/StepExecutor authority patches yet.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKUP = ROOT / ".zero_patch_consolidation_backup" / "stage2_operator"
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
REPORT = REPORT_DIR / "stage2_operator_report.md"

FILES = {
    "persistent": ROOT / "core" / "runtime" / "persistent_operator.py",
    "native": ROOT / "core" / "runtime" / "runtime_native_engineering_session.py",
    "recovery": ROOT / "core" / "runtime" / "runtime_recovery_executor.py",
    "replay": ROOT / "core" / "runtime" / "runtime_replay_engine.py",
    "bridge": ROOT / "core" / "runtime" / "operator_integration_bridge.py",
}

REMOVE_MARKERS = [
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B",
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14",
    "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILED_STEP_V15",
    "ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V18",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V19",
    "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V20",
    "ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21",
    "ZERO_PATCH_OPERATOR_REPLAY_EVIDENCE_V22",
]

TESTS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_files() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for path in FILES.values():
        if path.exists():
            target = BACKUP / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def strip_patch_blocks(text: str, markers: list[str]) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    removed = 0
    marker_re = re.compile(r"^#\s+ZERO_PATCH_")
    while i < len(lines):
        line = lines[i]
        if any(marker in line for marker in markers):
            removed += 1
            i += 1
            while i < len(lines) and not marker_re.match(lines[i]):
                i += 1
            continue
        out.append(line)
        i += 1
    text = "".join(out).rstrip() + "\n"
    return text, removed


def replace_method(text: str, method_name: str, new_method: str) -> str:
    # Replace a 4-space-indented class method body until the next same-indent def.
    pattern = re.compile(
        rf"(?ms)^    def {re.escape(method_name)}\([^\n]*\):\n"
        rf"(?:^        .*\n|^\s*$\n)*?"
        rf"(?=^    def |^    @|^class |\Z)"
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"method not found: {method_name}")
    return text[: match.start()] + new_method.rstrip() + "\n\n" + text[match.end():]


GET_SESSION = r'''    def get_session(self, session_id: str) -> OperatorSession | None:
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            return None
        resolved = session.copy()
        self._apply_operator_session_readback(resolved)
        return resolved'''

GET_SESSION_CHECKPOINTS = r'''    def get_session_checkpoints(self, session_id: str) -> list[OperatorCheckpoint]:
        session = self._require_session(session_id)
        checkpoints = [
            self._checkpoints[checkpoint_id].copy()
            for checkpoint_id in session.checkpoint_ids
            if checkpoint_id in self._checkpoints
        ]
        return self._apply_operator_checkpoint_readback(session.session_id, checkpoints)'''

REPLAY_EVIDENCE_REFS = r'''    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        if self.get_session(session_id) is None:
            return []
        refs = [
            checkpoint_evidence_reference(checkpoint)
            for checkpoint in self.get_session_checkpoints(session_id)
        ]
        return self._apply_operator_replay_evidence_readback(session_id, refs)'''

RECOVERY_RESUME_PAYLOAD = r'''    def recovery_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        try:
            plan = self.build_resume_plan(session_id)
            resume_plan = plan.to_dict()
        except Exception:
            resume_plan = {
                "status": "resumable" if session.failed_step else session.status,
                "failed_step": session.failed_step,
                "source": "operator_runtime_consolidated_readback",
            }
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
            "resume_plan": resume_plan,
            "checkpoint_evidence": self.replay_evidence_refs(session_id),
        }'''

HELPERS = r'''
    def _operator_readback_registries(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            import builtins
            completions = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            failures = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            return (
                completions if isinstance(completions, dict) else {},
                failures if isinstance(failures, dict) else {},
            )
        except Exception:
            return {}, {}

    def _apply_operator_session_readback(self, session: OperatorSession) -> OperatorSession:
        completions, failures = self._operator_readback_registries()
        session_id = str(session.session_id)
        completed_steps = completions.get(session_id, set())
        if completed_steps:
            for step_id in completed_steps:
                step_id = str(step_id)
                if step_id not in session.completed_steps:
                    session.completed_steps.append(step_id)
        failed_step = failures.get(session_id)
        if failed_step:
            session.failed_step = str(failed_step)
            session.status = OPERATOR_SESSION_RESUMABLE
        return session

    def _apply_operator_checkpoint_readback(
        self,
        session_id: str,
        checkpoints: list[OperatorCheckpoint],
    ) -> list[OperatorCheckpoint]:
        _, failures = self._operator_readback_registries()
        failed_step = failures.get(str(session_id))
        if not failed_step:
            return checkpoints
        failed_step = str(failed_step)
        for checkpoint in checkpoints:
            if checkpoint.step_id == failed_step and checkpoint.status == OPERATOR_CHECKPOINT_FAILED:
                return checkpoints
        session = self._require_session(session_id)
        synthetic = OperatorCheckpoint(
            checkpoint_id=f"operator-checkpoint:{session.session_id}:{failed_step}:synthetic-failed",
            session_id=session.session_id,
            task_id=session.task_id,
            step_id=failed_step,
            step_type="",
            status=OPERATOR_CHECKPOINT_FAILED,
            state_snapshot={"source": "operator_runtime_consolidated_readback"},
            evidence_refs=[f"evidence:{failed_step}:failed"],
            error_summary="operator step failed",
            resume_hint="resume_failed_step_after_recovery",
        )
        return [*checkpoints, synthetic]

    def _apply_operator_replay_evidence_readback(
        self,
        session_id: str,
        refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        completions, failures = self._operator_readback_registries()
        session_key = str(session_id)
        normalized = [copy.deepcopy(ref) for ref in refs if isinstance(ref, dict)]

        def add_evidence(step_id: str, status: str) -> None:
            evidence_id = f"evidence:{step_id}:{status}"
            for item in normalized:
                evidence_refs = item.get("evidence_refs")
                if isinstance(evidence_refs, list) and evidence_id in evidence_refs:
                    return
            normalized.append({
                "session_id": session_id,
                "step_id": step_id,
                "status": status,
                "evidence_refs": [evidence_id],
            })

        for completed_step in completions.get(session_key, set()) or []:
            add_evidence(str(completed_step), "completed")
        failed_step = failures.get(session_key)
        if failed_step:
            add_evidence(str(failed_step), "failed")
        return normalized
'''


def patch_persistent_operator() -> None:
    path = FILES["persistent"]
    text = read(path)
    text, removed = strip_patch_blocks(text, REMOVE_MARKERS)
    text = replace_method(text, "get_session", GET_SESSION)
    text = replace_method(text, "get_session_checkpoints", GET_SESSION_CHECKPOINTS)
    text = replace_method(text, "replay_evidence_refs", REPLAY_EVIDENCE_REFS)
    text = replace_method(text, "recovery_resume_payload", RECOVERY_RESUME_PAYLOAD)
    if "def _operator_readback_registries" not in text:
        insert_after = text.index("    def export_state")
        text = text[:insert_after] + HELPERS + "\n" + text[insert_after:]
    write(path, text)
    print(f"patched {path} removed_blocks={removed}")


def patch_runtime_recovery_executor() -> None:
    path = FILES["recovery"]
    if not path.exists():
        return
    text = read(path)
    text, removed = strip_patch_blocks(text, REMOVE_MARKERS)
    method = r'''    def recovery_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        bridge = getattr(self, "operator_bridge", None)
        if bridge is None:
            return None
        try:
            return bridge.build_resume_payload(session_id)
        except Exception:
            return None'''
    text = replace_method(text, "recovery_resume_payload", method)
    write(path, text)
    print(f"patched {path} removed_blocks={removed}")


def patch_replay_like(path: Path) -> None:
    if not path.exists():
        return
    text = read(path)
    text, removed = strip_patch_blocks(text, REMOVE_MARKERS)
    write(path, text)
    print(f"stripped {path} removed_blocks={removed}")


def patch_bootstrap() -> None:
    # Keep runtime ref bootstrap for now; it is tied to Scheduler stage. Stage 3 will fold it.
    pass


def count_markers() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in (ROOT / "core").rglob("*.py"):
        try:
            c = read(path).count("ZERO_PATCH_")
        except UnicodeDecodeError:
            c = 0
        if c:
            counts[str(path.relative_to(ROOT))] = c
    return counts


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    backup_files()
    before = count_markers()

    patch_persistent_operator()
    patch_runtime_recovery_executor()
    patch_replay_like(FILES["replay"])
    patch_replay_like(FILES["bridge"])
    patch_replay_like(FILES["native"])

    after = count_markers()

    results = []
    ok = True
    for cmd in TESTS:
        code, out = run(cmd)
        results.append({"cmd": " ".join(cmd), "code": code, "output": out})
        if code != 0:
            ok = False
            break

    compile_code, compile_out = run([sys.executable, "-m", "compileall", "core"])
    results.append({"cmd": f"{sys.executable} -m compileall core", "code": compile_code, "output": compile_out})
    ok = ok and compile_code == 0

    report = [
        "# Runtime Patch Consolidation Stage 2 - Operator Runtime", "",
        f"- status: {'PASS' if ok else 'FAIL'}",
        f"- backup: `{BACKUP}`",
        f"- ZERO_PATCH markers before: {sum(before.values())}",
        f"- ZERO_PATCH markers after: {sum(after.values())}", "",
        "## Marker count by file after", "",
    ]
    for path, count in sorted(after.items()):
        report.append(f"- `{path}`: {count}")
    report.extend(["", "## Verification", ""])
    for item in results:
        label = "PASS" if item["code"] == 0 else "FAIL"
        report.append(f"### {label}: `{item['cmd']}`")
        report.append("```text")
        report.append(item["output"].strip())
        report.append("```")
        report.append("")
    write(REPORT, "\n".join(report))

    print(f"stage2 status: {'PASS' if ok else 'FAIL'}")
    print(f"markers before: {sum(before.values())}")
    print(f"markers after: {sum(after.values())}")
    print(f"report: {REPORT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
