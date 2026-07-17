from __future__ import annotations

from core.runtime.task_runtime import project_runtime_status
import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = "zero.aer.persistent_engineering_session.v1"


def _now() -> float:
    return time.time()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _repo_root(value: Any) -> Path:
    try:
        return Path(str(value or ".")).resolve()
    except Exception:
        return Path(".").resolve()


class PersistentEngineeringSession:
    """Persistent engineering session state for AER runtime work.

    This class is intentionally state/persistence only.

    Ownership boundary:
    - It does not plan.
    - It does not execute StepExecutor.
    - It does not call ToolRegistry.
    - It does not mutate source files except its own session JSON under
      workspace/persistent_engineering_sessions.
    - It records workflow identity, runtime session lineage, checkpoints,
      artifacts, resume points, and continuation records so a later planner /
      orchestrator layer can resume the engineering task with explicit state.
    """

    def __init__(
        self,
        *,
        repo_root: Path | str = ".",
        workflow_id: str = "",
        session_id: str = "",
        goal: str = "",
    ) -> None:
        self.repo_root = _repo_root(repo_root)
        self.root = self.repo_root / "workspace" / "persistent_engineering_sessions"
        self.workflow_id = _clean_text(workflow_id) or _short_id("workflow")
        self.session_id = _clean_text(session_id) or _short_id("engineering_session")
        self.goal = _clean_text(goal)
        self.path = self.root / self.workflow_id / f"{self.session_id}.json"

    @classmethod
    def create_from_runtime_result(
        cls,
        *,
        repo_root: Path | str = ".",
        runtime_result: Dict[str, Any],
        goal: str = "",
    ) -> "PersistentEngineeringSession":
        payload = _safe_dict(runtime_result)
        orchestrator = payload.get("persistent_runtime_orchestrator")
        if not isinstance(orchestrator, dict):
            dispatch = payload.get("planner_runtime_dispatch")
            if isinstance(dispatch, dict):
                orchestrator = dispatch.get("orchestrator")
        if not isinstance(orchestrator, dict):
            orchestrator = {}

        workflow_id = (
            _clean_text(payload.get("workflow_id"))
            or _clean_text(orchestrator.get("task_id"))
            or _short_id("workflow")
        )
        session_id = (
            _clean_text(payload.get("session_id"))
            or _clean_text(orchestrator.get("session_id"))
            or _short_id("engineering_session")
        )
        session_goal = (
            _clean_text(goal)
            or _clean_text(payload.get("goal"))
            or _clean_text(orchestrator.get("goal"))
            or _clean_text(payload.get("final_answer"))
        )

        session = cls(
            repo_root=repo_root,
            workflow_id=workflow_id,
            session_id=session_id,
            goal=session_goal,
        )
        session.initialize()
        session.attach_runtime_result(runtime_result=payload)
        return session

    def initialize(self) -> Dict[str, Any]:
        existing = _read_json(self.path)
        if existing:
            return existing

        payload = {
            "ok": True,
            "schema": SCHEMA,
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": "initialized",
            "created_at": _now(),
            "updated_at": _now(),
            "runtime_sessions": [],
            "checkpoints": [],
            "artifacts": [],
            "resume_points": [],
            "continuations": [],
            "events": [
                {
                    "event": "session_initialized",
                    "created_at": _now(),
                    "workflow_id": self.workflow_id,
                    "session_id": self.session_id,
                }
            ],
            "boundary": {
                "state_only": True,
                "does_not_execute": True,
                "does_not_call_tool_registry": True,
                "does_not_mutate_project_files": True,
                "planner_remains_planning_only": True,
                "step_executor_remains_execution_endpoint": True,
            },
        }
        self._save(payload)
        return payload

    def load(self) -> Dict[str, Any]:
        payload = _read_json(self.path)
        if not payload:
            return self.initialize()
        return payload

    def _save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["updated_at"] = _now()
        payload["session_record_path"] = str(self.path)
        _write_json(self.path, payload)
        return payload

    def record_event(self, event: str, **fields: Any) -> Dict[str, Any]:
        payload = self.load()
        payload.setdefault("events", []).append(
            {
                "event": _clean_text(event) or "event",
                "created_at": _now(),
                **copy.deepcopy(fields),
            }
        )
        return self._save(payload)

    def attach_runtime_result(self, *, runtime_result: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.load()
        result = _safe_dict(runtime_result)

        orchestrator = result.get("persistent_runtime_orchestrator")
        if not isinstance(orchestrator, dict):
            dispatch = result.get("planner_runtime_dispatch")
            if isinstance(dispatch, dict):
                orchestrator = dispatch.get("orchestrator")
        if not isinstance(orchestrator, dict):
            orchestrator = {}

        multi = orchestrator.get("multi_cycle_engineering_loop")
        if not isinstance(multi, dict):
            multi = {}

        runtime_session_record = {
            "created_at": _now(),
            "ok": bool(result.get("ok", orchestrator.get("ok", False))),
            "status": _clean_text(orchestrator.get("status")) or _clean_text(result.get("status")) or "unknown",
            "orchestrator_session_id": _clean_text(orchestrator.get("session_id")),
            "orchestrator_session_record_path": _clean_text(orchestrator.get("session_record_path")),
            "orchestrator_session_dir": _clean_text(orchestrator.get("session_dir")),
            "cycle_count": multi.get("cycle_count", orchestrator.get("cycle_count", 0)),
            "cycle_result_count": multi.get("cycle_result_count", orchestrator.get("cycle_result_count", 0)),
            "closure_count": multi.get("closure_count", orchestrator.get("closure_count", 0)),
        }
        payload.setdefault("runtime_sessions", []).append(runtime_session_record)

        for cycle in _safe_list(multi.get("cycle_results")):
            if not isinstance(cycle, dict):
                continue
            runtime = cycle.get("runtime")
            if not isinstance(runtime, dict):
                continue
            for checkpoint in _safe_list(runtime.get("checkpoints")):
                if isinstance(checkpoint, dict):
                    payload.setdefault("checkpoints", []).append(
                        {
                            "created_at": _now(),
                            "cycle_id": cycle.get("cycle_id"),
                            "checkpoint_path": checkpoint.get("checkpoint_path"),
                            "checkpoint_index": checkpoint.get("checkpoint_index"),
                            "status": checkpoint.get("status"),
                        }
                    )

        project_runtime_status(payload, "runtime_attached", owner="core/runtime/persistent_engineering_session.py")
        payload.setdefault("events", []).append(
            {
                "event": "runtime_result_attached",
                "created_at": _now(),
                "runtime_status": runtime_session_record["status"],
                "cycle_count": runtime_session_record["cycle_count"],
                "closure_count": runtime_session_record["closure_count"],
            }
        )
        return self._save(payload)

    def record_artifact(
        self,
        *,
        path: str,
        kind: str = "artifact",
        description: str = "",
        source_step: str = "",
    ) -> Dict[str, Any]:
        payload = self.load()
        payload.setdefault("artifacts", []).append(
            {
                "created_at": _now(),
                "path": _clean_text(path),
                "kind": _clean_text(kind) or "artifact",
                "description": _clean_text(description),
                "source_step": _clean_text(source_step),
            }
        )
        return self._save(payload)

    def create_resume_point(
        self,
        *,
        reason: str,
        cursor: Optional[Dict[str, Any]] = None,
        required_inputs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload = self.load()
        resume_id = _short_id("resume")
        record = {
            "resume_id": resume_id,
            "created_at": _now(),
            "reason": _clean_text(reason),
            "cursor": _safe_dict(cursor),
            "required_inputs": _safe_list(required_inputs),
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "status": "open",
        }
        payload.setdefault("resume_points", []).append(record)
        project_runtime_status(payload, "resume_point_open", owner="core/runtime/persistent_engineering_session.py")
        payload.setdefault("events", []).append(
            {
                "event": "resume_point_created",
                "created_at": _now(),
                "resume_id": resume_id,
                "reason": record["reason"],
            }
        )
        self._save(payload)
        return record

    def record_continuation(
        self,
        *,
        resume_id: str,
        continuation_result: Optional[Dict[str, Any]] = None,
        status: str = "continued",
    ) -> Dict[str, Any]:
        payload = self.load()
        resume_id = _clean_text(resume_id)
        record = {
            "continuation_id": _short_id("continuation"),
            "created_at": _now(),
            "resume_id": resume_id,
            "status": _clean_text(status) or "continued",
            "continuation_result": _safe_dict(continuation_result),
        }
        payload.setdefault("continuations", []).append(record)

        for resume in payload.get("resume_points", []):
            if isinstance(resume, dict) and resume.get("resume_id") == resume_id:
                resume["status"] = "continued"
                resume["continued_at"] = record["created_at"]

        project_runtime_status(payload, "continued", owner="core/runtime/persistent_engineering_session.py")
        payload.setdefault("events", []).append(
            {
                "event": "continuation_recorded",
                "created_at": _now(),
                "resume_id": resume_id,
                "continuation_id": record["continuation_id"],
            }
        )
        self._save(payload)
        return record

    def summary(self) -> Dict[str, Any]:
        payload = self.load()
        open_resume_points = [
            resume for resume in payload.get("resume_points", [])
            if isinstance(resume, dict) and resume.get("status") == "open"
        ]
        return {
            "ok": True,
            "schema": SCHEMA,
            "workflow_id": payload.get("workflow_id"),
            "session_id": payload.get("session_id"),
            "goal": payload.get("goal"),
            "status": payload.get("status"),
            "session_record_path": str(self.path),
            "runtime_session_count": len(payload.get("runtime_sessions", [])),
            "checkpoint_count": len(payload.get("checkpoints", [])),
            "artifact_count": len(payload.get("artifacts", [])),
            "resume_point_count": len(payload.get("resume_points", [])),
            "open_resume_point_count": len(open_resume_points),
            "continuation_count": len(payload.get("continuations", [])),
            "event_count": len(payload.get("events", [])),
            "boundary": copy.deepcopy(payload.get("boundary", {})),
        }


def create_persistent_engineering_session_from_runtime_result(
    *,
    repo_root: Path | str = ".",
    runtime_result: Dict[str, Any],
    goal: str = "",
) -> Dict[str, Any]:
    session = PersistentEngineeringSession.create_from_runtime_result(
        repo_root=repo_root,
        runtime_result=runtime_result,
        goal=goal,
    )
    return session.summary()


__all__ = [
    "SCHEMA",
    "PersistentEngineeringSession",
    "create_persistent_engineering_session_from_runtime_result",
]
