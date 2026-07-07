from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


from core.runtime.execution_gateway import safe_subprocess_run


GIT_COMMIT_ACTUATOR_SCHEMA = "zero.runtime.git_commit_actuator.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _run_git(repo_root: Path, args: list[str]) -> dict[str, Any]:
    return safe_subprocess_run(
        ("git", *args),
        cwd=str(repo_root),
        timeout=120,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _report_only_commit_id(
    *,
    package_id: str,
    task_id: str,
    run_id: str,
    diff_text: str,
) -> str:
    material = "|".join(
        [
            _text(package_id),
            _text(task_id),
            _text(run_id),
            _text(diff_text),
        ]
    )
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

        if not status["ok"]:
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_status_failed",
                "denial_reason": "git_status_failed",
                "stderr": status.get("stderr", ""),
            }

        diff_text = status.get("stdout", "").strip()
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
            return record | {
                "denial_reason": "",
                "git_commit_actuator_record_path": str(evidence_path),
            }

        add = _run_git(repo_root, ["add", "-A"])

        if not add["ok"]:
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_add_failed",
                "denial_reason": "git_add_failed",
                "stderr": add.get("stderr", ""),
            }

        message = f"ZERO governed runtime commit: {_text(package_id)} / {_text(task_id)}"

        commit = _run_git(
            repo_root,
            [
                "commit",
                "-m",
                message,
            ],
        )

        if not commit["ok"]:
            return {
                "actuator_status": "blocked",
                "commit_applied": False,
                "commit_id": "",
                "runtime_commit_apply_status": "blocked_git_commit_failed",
                "denial_reason": "git_commit_failed",
                "stdout": commit.get("stdout", ""),
                "stderr": commit.get("stderr", ""),
            }

        rev = _run_git(repo_root, ["rev-parse", "HEAD"])

        commit_id = ""
        if rev["ok"]:
            commit_id = rev.get("stdout", "").strip()

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
            "git_status_before_commit": diff_text,
            "non_mainline_issues": list(
                governed_commit_record.get("non_mainline_issues") or []
            ),
        }

        _write_json(evidence_path, record)

        return record | {
            "denial_reason": "",
            "git_commit_actuator_record_path": str(evidence_path),
        }


__all__ = [
    "GIT_COMMIT_ACTUATOR_SCHEMA",
    "RuntimeGitCommitActuator",
]