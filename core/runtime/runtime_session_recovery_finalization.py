from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _session_dirs(repo_root: Path) -> List[Path]:
    root = repo_root / "workspace" / "runtime_sessions"
    if not root.exists():
        return []
    return sorted(
        [path for path in root.glob("runtime_session_*") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _resume_journals(repo_root: Path) -> List[Path]:
    root = repo_root / "workspace" / "runtime_session_resumes"
    if not root.exists():
        return []
    return sorted(
        [path for path in root.glob("*resume_journal.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _load_recovery_marker(session_dir: Path) -> Dict[str, Any]:
    marker = _read_json(session_dir / "recovery_marker.json")
    if marker:
        return marker
    return {}


def _load_superseded_marker(session_dir: Path) -> Dict[str, Any]:
    return _read_json(session_dir / "recovery_marker.superseded.json")


def find_recovery_lineage(repo_root: Path, source_session_id: str = "") -> Dict[str, Any]:
    sessions = _session_dirs(repo_root)
    if source_session_id:
        sessions = [repo_root / "workspace" / "runtime_sessions" / source_session_id]

    session_records: List[Dict[str, Any]] = []
    for session_dir in sessions:
        if not session_dir.exists():
            continue
        state = _read_json(session_dir / "session_state.json")
        journal = _read_json(session_dir / "session_journal.json")
        marker = _load_recovery_marker(session_dir)
        superseded_marker = _load_superseded_marker(session_dir)
        if not marker and not superseded_marker and state.get("status") != "recovery_required":
            continue
        session_records.append(
            {
                "session_id": session_dir.name,
                "session_dir": str(session_dir),
                "state": state,
                "journal": journal,
                "recovery_marker": marker,
                "superseded_marker": superseded_marker,
                "mtime": session_dir.stat().st_mtime,
            }
        )

    resume_records: List[Dict[str, Any]] = []
    for path in _resume_journals(repo_root):
        payload = _read_json(path)
        if not payload:
            continue
        if source_session_id and payload.get("source_session_id") != source_session_id:
            continue
        payload["resume_journal_path"] = str(path)
        resume_records.append(payload)

    return {
        "schema": "zero.aer.runtime_session_recovery_lineage.v1",
        "source_session_id": source_session_id,
        "sessions": session_records,
        "resumes": resume_records,
        "session_count": len(session_records),
        "resume_count": len(resume_records),
        "created_at": time.time(),
    }


def finalize_runtime_session_recovery(
    *,
    repo_root: Path,
    task_id: str,
    goal: str,
    source_session_id: str = "",
    max_resume_depth: int = 2,
) -> Dict[str, Any]:
    """Finalize session recovery lineage without creating hidden mutations.

    This layer does not force another resume by default.  It closes and records:
    - resume lineage
    - supersede chain
    - retry depth policy
    - escalation state
    - replay linkage
    - bounded recovery status

    If prior resume succeeded, it marks the recovery as finalized.
    If prior resume failed or depth is exhausted, it escalates safely.
    """

    lineage = find_recovery_lineage(repo_root, source_session_id=source_session_id)
    resumes = lineage.get("resumes") if isinstance(lineage.get("resumes"), list) else []
    sessions = lineage.get("sessions") if isinstance(lineage.get("sessions"), list) else []

    latest_resume = resumes[0] if resumes else {}
    latest_resume_ok = bool(latest_resume.get("ok"))
    latest_resume_status = str(latest_resume.get("status") or "")
    latest_resumed_session_id = str(latest_resume.get("resumed_session_id") or "")
    resume_depth = len(resumes)

    recovery_finalized = latest_resume_ok and latest_resume_status == "resumed"
    depth_exhausted = resume_depth >= max(1, int(max_resume_depth or 1))
    escalation_required = not recovery_finalized and depth_exhausted

    root = repo_root / "workspace" / "runtime_session_recovery_finalizations"
    root.mkdir(parents=True, exist_ok=True)
    finalization_path = root / f"{task_id}_recovery_finalization.json"

    supersede_chain: List[Dict[str, Any]] = []
    for session in sessions:
        marker = session.get("superseded_marker") if isinstance(session.get("superseded_marker"), dict) else {}
        recovery_marker = session.get("recovery_marker") if isinstance(session.get("recovery_marker"), dict) else {}
        if marker or recovery_marker:
            supersede_chain.append(
                {
                    "session_id": session.get("session_id"),
                    "status": (session.get("state") or {}).get("status"),
                    "recovery_marker_path": str(Path(str(session.get("session_dir"))) / "recovery_marker.json"),
                    "superseded_by_session_id": marker.get("superseded_by_session_id"),
                    "superseded_by_resume_task_id": marker.get("superseded_by_resume_task_id"),
                    "superseded_at": marker.get("superseded_at"),
                    "resume_ok": marker.get("resume_ok"),
                }
            )

    replay_links: List[Dict[str, Any]] = []
    for session in sessions:
        session_dir = Path(str(session.get("session_dir")))
        replay_path = session_dir / "session_replay.json"
        journal_path = session_dir / "session_journal.json"
        replay_links.append(
            {
                "session_id": session.get("session_id"),
                "replay_path": str(replay_path),
                "journal_path": str(journal_path),
                "replay_exists": replay_path.exists(),
                "journal_exists": journal_path.exists(),
            }
        )

    record = {
        "ok": recovery_finalized or escalation_required,
        "schema": "zero.aer.runtime_session_recovery_finalization.v1",
        "task_id": task_id,
        "goal": goal,
        "source_session_id": source_session_id,
        "status": "finalized" if recovery_finalized else ("escalated" if escalation_required else "pending_retry"),
        "recovery_finalized": recovery_finalized,
        "escalation_required": escalation_required,
        "resume_depth": resume_depth,
        "max_resume_depth": max_resume_depth,
        "latest_resume_ok": latest_resume_ok,
        "latest_resume_status": latest_resume_status,
        "latest_resumed_session_id": latest_resumed_session_id,
        "latest_resume_journal_path": latest_resume.get("resume_journal_path") or latest_resume.get("resume_journal_path"),
        "lineage": lineage,
        "supersede_chain": supersede_chain,
        "replay_links": replay_links,
        "finalization_path": str(finalization_path),
        "created_at": time.time(),
        "policy": {
            "max_resume_depth_enforced": True,
            "resume_retry_allowed": not depth_exhausted and not recovery_finalized,
            "manual_review_required_on_escalation": escalation_required,
            "no_hidden_mutation_shortcut": True,
        },
        "boundary": {
            "resume_lineage_recorded": True,
            "failure_lineage_recorded": True,
            "resume_replay_linkage_recorded": True,
            "recovery_bounded": True,
            "session_supersede_chain_recorded": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
        },
    }

    if escalation_required:
        incident = {
            "schema": "zero.aer.runtime_session_recovery_finalization.incident.v1",
            "task_id": task_id,
            "source_session_id": source_session_id,
            "reason": "resume_depth_exhausted_or_latest_resume_failed",
            "resume_depth": resume_depth,
            "max_resume_depth": max_resume_depth,
            "latest_resume_status": latest_resume_status,
            "created_at": time.time(),
        }
        incident_path = root / f"{task_id}_recovery_escalation_incident.json"
        _write_json(incident_path, incident)
        record["runtime_incident"] = incident
        record["runtime_incident_path"] = str(incident_path)

    _write_json(finalization_path, record)
    return record
