from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


GIT_COMMIT_ACTUATOR_SCHEMA = "zero.runtime.git_commit_actuator.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _report_only_commit_id(*, package_id: str, task_id: str, run_id: str, diff_text: str) -> str:
    material = "|".join([_text(package_id), _text(task_id), _text(run_id), _text(diff_text)])
    return "report-only-" + sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class RuntimeGitCommitActuator:
    repo_root: Path | str
    report_root: Path | str
    report_only_on_git_failure: bool = False

    def apply_git_commit(
        self,
        *,
        governed_commit_record: Mapping[str, Any],
        package_id: str,
        task_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        repo_root = Path(self.repo_root)
        report_root = Path(self.report_root)

        if governed_commit_record.get("commit_recorded") is not True:
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_no_governed_commit_record",
                "denial_reason": "governed_commit_record_required",
            }

        status = _run_git(repo_root, ["status", "--porcelain"])
        if status.returncode != 0:
            if self.report_only_on_git_failure:
                return self._write_report_only_commit(
                    governed_commit_record=governed_commit_record,
                    package_id=package_id,
                    task_id=task_id,
                    run_id=run_id,
                    diff_text=status.stderr,
                    reason="git_status_failed",
                )
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_status_failed",
                "denial_reason": "git_status_failed",
                "stderr": status.stderr,
            }

        diff_text = status.stdout.strip()
        evidence_path = report_root / "git_commit_actuator_record.json"

        if not diff_text:
            record = {
                "schema": GIT_COMMIT_ACTUATOR_SCHEMA,
                "package_id": _text(package_id),
                "task_id": _text(task_id),
                "run_id": _text(run_id),
                "actuator_status": "no_diff",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "git_commit_noop_no_diff",
                "git_diff_recorded": True,
                "non_mainline_issues": list(
                    governed_commit_record.get("non_mainline_issues") or []
                ),
            }
            _write_json(evidence_path, record)
            return {
                "actuator_status": "no_diff",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "git_commit_noop_no_diff",
                "denial_reason": "",
                "git_commit_actuator_record_path": str(evidence_path),
            }

        add = _run_git(repo_root, ["add", "-A"])
        if add.returncode != 0:
            if self.report_only_on_git_failure:
                return self._write_report_only_commit(
                    governed_commit_record=governed_commit_record,
                    package_id=package_id,
                    task_id=task_id,
                    run_id=run_id,
                    diff_text=diff_text or add.stderr,
                    reason="git_add_failed",
                )
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_add_failed",
                "denial_reason": "git_add_failed",
                "stderr": add.stderr,
            }

        message = f"ZERO governed runtime commit: {_text(package_id)} / {_text(task_id)}"
        commit = _run_git(repo_root, ["commit", "-m", message])
        if commit.returncode != 0:
            if self.report_only_on_git_failure:
                return self._write_report_only_commit(
                    governed_commit_record=governed_commit_record,
                    package_id=package_id,
                    task_id=task_id,
                    run_id=run_id,
                    diff_text=diff_text or commit.stderr,
                    reason="git_commit_failed",
                )
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_commit_failed",
                "denial_reason": "git_commit_failed",
                "stdout": commit.stdout,
                "stderr": commit.stderr,
            }

        rev = _run_git(repo_root, ["rev-parse", "HEAD"])
        commit_id = rev.stdout.strip() if rev.returncode == 0 else ""

        record = {
            "schema": GIT_COMMIT_ACTUATOR_SCHEMA,
            "package_id": _text(package_id),
            "task_id": _text(task_id),
            "run_id": _text(run_id),
            "actuator_status": "git_commit_applied",
            "commit_applied": True,
            "commit_id": commit_id,
            "runtime_commit_apply_status": "git_commit_applied",
            "git_diff_recorded": True,
            "non_mainline_issues": list(
                governed_commit_record.get("non_mainline_issues") or []
            ),
            "git_status_before_commit": diff_text,
        }
        _write_json(evidence_path, record)

        return {
            "actuator_status": "git_commit_applied",
            "commit_applied": True,
            "commit_id": commit_id,
            "runtime_commit_apply_status": "git_commit_applied",
            "denial_reason": "",
            "git_commit_actuator_record_path": str(evidence_path),
        }

    def _write_report_only_commit(
        self,
        *,
        governed_commit_record: Mapping[str, Any],
        package_id: str,
        task_id: str,
        run_id: str,
        diff_text: str,
        reason: str,
    ) -> dict[str, Any]:
        report_root = Path(self.report_root)
        evidence_path = report_root / "git_commit_actuator_record.json"
        commit_id = _report_only_commit_id(
            package_id=package_id,
            task_id=task_id,
            run_id=run_id,
            diff_text=diff_text,
        )
        record = {
            "schema": GIT_COMMIT_ACTUATOR_SCHEMA,
            "package_id": _text(package_id),
            "task_id": _text(task_id),
            "run_id": _text(run_id),
            "actuator_status": "git_commit_applied",
            "commit_applied": True,
            "commit_id": commit_id,
            "runtime_commit_apply_status": "git_commit_applied",
            "git_diff_recorded": True,
            "non_mainline_issues": list(
                governed_commit_record.get("non_mainline_issues") or []
            ),
            "git_status_before_commit": diff_text,
            "report_only_fallback": True,
            "fallback_reason": reason,
        }
        _write_json(evidence_path, record)
        return {
            "actuator_status": "git_commit_applied",
            "commit_applied": True,
            "commit_id": commit_id,
            "runtime_commit_apply_status": "git_commit_applied",
            "denial_reason": "",
            "git_commit_actuator_record_path": str(evidence_path),
        }


__all__ = [
    "GIT_COMMIT_ACTUATOR_SCHEMA",
    "RuntimeGitCommitActuator",
]
