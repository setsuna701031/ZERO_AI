from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, time_text

CONTRACT = "zero.runtime.natural_language_mission_bootstrap.v1"
INTERPRETER_VERSION = "deterministic-baseline-v1"


def _unsafe(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _safe_relative(raw: str, target_root: Path) -> str:
    text = raw.strip().strip("'\"，,。:：") .replace("\\", "/")
    if not text:
        raise ValueError("natural_language_path_required")
    candidate = Path(text)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(target_root):
            raise ValueError("natural_language_path_outside_target_root")
        text = resolved.relative_to(target_root).as_posix()
    pure = PurePosixPath(text)
    if pure.is_absolute() or ":" in text or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("unsafe_natural_language_path")
    resolved = (target_root / Path(*pure.parts)).resolve(strict=False)
    if not resolved.is_relative_to(target_root) or _unsafe(resolved):
        raise ValueError("unsafe_natural_language_path")
    return pure.as_posix()


def normalize_natural_language_mission(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise ValueError("empty_natural_language_mission")
    if len(value) > 8000:
        raise ValueError("natural_language_mission_too_long")
    return value


def interpret_natural_language_mission(text: str, *, target_root: Any) -> dict[str, Any]:
    normalized = normalize_natural_language_mission(text)
    root = Path(target_root).resolve(strict=True)
    lower = normalized.casefold()
    intents: list[dict[str, Any]] = []

    # Commands are represented as validation intent only; no shell string is retained or executed.
    pytest_match = re.search(r"(?:執行|運行|run)\s+(?:python\s+-m\s+)?pytest\s+([^\s，,。]+)(?:\s+-q)?", normalized, re.I)
    if pytest_match:
        test_path = _safe_relative(pytest_match.group(1), root)
        intents.append({"operation": "run_tests", "path": test_path, "validation_profile": "pytest", "supported": True, "confidence": 1.0, "manual_review_required": True})

    directory_match = re.search(r"(?:建立|新增|創建|create)\s*(?:一個)?\s*(?:資料夾|目錄|directory|folder)\s*[:：]?\s*([^\s，,。]+)", normalized, re.I)
    if directory_match is None:
        directory_match = re.search(r"(?:建立|新增|創建|create)\s+([^\s，,。]+)\s+(?:資料夾|目錄|directory|folder)", normalized, re.I)
    if directory_match:
        intents.append({"operation": "create_directory", "path": _safe_relative(directory_match.group(1), root), "supported": True, "confidence": 1.0, "manual_review_required": True})

    file_match = re.search(r"(?:建立|新增|創建|create)(?:一個)?(?:檔案|文件|file)?\s*([^\s，,。]+\.[A-Za-z0-9_-]+)(?:\s*(?:，|,)?\s*(?:內容(?:是|為)|with\s+content)\s*[:：]?\s*(.+?))?(?:\s*(?:，|,)?\s*(?:然後|並且|and then)\s*(?:確認|檢查|verify).*)?$", normalized, re.I)
    if file_match:
        relative = _safe_relative(file_match.group(1), root)
        content = (file_match.group(2) or "").strip().rstrip("。")
        intents.append({"operation": "create_file", "path": relative, "content": content, "supported": True, "confidence": 1.0 if content else 0.8, "manual_review_required": True})
        if any(token in lower for token in ("確認", "檢查", "verify", "check")):
            intents.append({"operation": "check_exists", "path": relative, "supported": True, "confidence": 1.0, "manual_review_required": False})

    if not file_match:
        check_match = re.search(r"(?:檢查|確認|check whether|check)\s+([^\s，,。]+)(?:\s+(?:是否)?存在|\s+exists?)", normalized, re.I)
        read_match = re.search(r"(?:讀取|閱讀|read)\s+([^\s，,。]+)", normalized, re.I)
        if check_match:
            intents.append({"operation": "check_exists", "path": _safe_relative(check_match.group(1), root), "supported": True, "confidence": 1.0, "manual_review_required": False})
        elif read_match:
            intents.append({"operation": "read_file", "path": _safe_relative(read_match.group(1), root), "supported": True, "confidence": 1.0, "manual_review_required": False})

    reasons = [] if intents else ["unsupported_or_ambiguous_natural_language"]
    value = {"normalized_input": normalized, "interpreter_version": INTERPRETER_VERSION, "structured_intents": intents, "supported": bool(intents), "manual_review_required": not intents or any(i["manual_review_required"] for i in intents), "reasons": reasons}
    value["interpretation_fingerprint"] = fingerprint(value)
    return value


def _goal_plan(interpretation: Mapping[str, Any]) -> list[dict[str, Any]]:
    goals: list[dict[str, Any]] = []
    previous = None
    for index, intent in enumerate(interpretation.get("structured_intents") or []):
        operation, path = intent["operation"], intent["path"]
        kind = "validate" if operation == "run_tests" else ("inspect" if operation in {"check_exists", "read_file"} else "modify")
        goal_id = f"natural-goal-{index + 1}-{fingerprint({'operation': operation, 'path': path})[:12]}"
        goal = {"goal_id": goal_id, "goal_title": f"{operation.replace('_', ' ').title()}: {path}", "goal_description": f"Perform the structured {operation} operation for {path} through the existing controlled Mission Runtime.", "goal_type": kind, "goal_status": "pending", "priority": 0, "depends_on": [previous] if previous else [], "required_capabilities": ["validate" if kind == "validate" else ("inspect" if kind == "inspect" else "modify")], "target_scope": [path], "acceptance_criteria": [f"Structured operation {operation} is evidenced for {path}"], "validation_requirements": [f"Verify {path} using persisted runtime evidence"], "operator_confirmation_required": bool(intent.get("manual_review_required", True)), "natural_operation": operation, "natural_operation_inputs": {k: deepcopy(v) for k, v in intent.items() if k in {"path", "content", "validation_profile"}}, "max_attempts": 3}
        goals.append(goal); previous = goal_id
    return goals


def _state_root(workspace_root: Path, target_root: Path, identity: str) -> Path:
    base = workspace_root
    if base == target_root or base.is_relative_to(target_root):
        base = target_root.parent / ".zero_ai_runtime"
    return base / "mission_runtime" / identity


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(path) or _unsafe(path.parent): raise ValueError("unsafe_bootstrap_artifact_path")
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)


class NaturalLanguageMissionBootstrap:
    def prepare(self, natural_language: str, *, workspace_root: Any, target_root: Any = None, operator_id: str = "zero-mission-cli", memory_context: Mapping[str, Any] | None = None, force_new: bool = False, now: Any = None) -> dict[str, Any]:
        workspace = Path(workspace_root).resolve(strict=True); target = Path(target_root or workspace).resolve(strict=True)
        interpretation = interpret_natural_language_mission(natural_language, target_root=target)
        context = deepcopy(dict(memory_context)) if isinstance(memory_context, Mapping) else None
        identity_seed = {"input": interpretation["normalized_input"], "workspace": str(workspace).casefold(), "target": str(target).casefold(), "memory_context_fingerprint": context.get("context_fingerprint") if context else None, "force": time_text(now) if force_new else None}
        bootstrap_id = f"mission-bootstrap-{fingerprint(identity_seed)[:20]}"; root = _state_root(workspace, target, bootstrap_id)
        artifact_path = root / "bootstrap.json"
        if artifact_path.exists() and not force_new:
            existing = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
            if existing.get("artifact_fingerprint") != fingerprint({k: v for k, v in existing.items() if k != "artifact_fingerprint"}): raise ValueError("bootstrap_artifact_fingerprint_mismatch")
            return existing
        at = time_text(now)
        baseline_goal_plan = _goal_plan(interpretation) if interpretation["supported"] else []
        planning_feedback = None
        planning_feedback_status = "created"
        planning_feedback_error = None
        guided = {"goal_plan": baseline_goal_plan, "goal_plan_before_feedback": [], "goal_plan_after_feedback": [], "applied_recommendations": [], "ignored_recommendations": []}
        try:
            from core.runtime.runtime_agent_planning_feedback import build_agent_planning_feedback, save_planning_feedback
            from core.runtime.runtime_memory_guided_goal_planner import apply_planning_feedback_to_goal_plan, summarize_goal_plan
            planning_feedback = build_agent_planning_feedback(
                interpretation["normalized_input"], structured_intents=interpretation["structured_intents"],
                memory_context=context, workspace_root=workspace, target_root=target,
                safety_constraints=["controlled_execution", "path_containment", "operator_approval"], now=now,
            )
            guided["goal_plan_before_feedback"] = summarize_goal_plan(baseline_goal_plan)
            guided["goal_plan_after_feedback"] = summarize_goal_plan(baseline_goal_plan)
            if baseline_goal_plan:
                guided = apply_planning_feedback_to_goal_plan(baseline_goal_plan, planning_feedback)
            save_planning_feedback(planning_feedback, root / "planning-feedback.json")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            planning_feedback_status = "failed"
            planning_feedback_error = str(exc)
            planning_feedback = None
            from core.runtime.runtime_memory_guided_goal_planner import summarize_goal_plan
            guided["goal_plan_before_feedback"] = summarize_goal_plan(baseline_goal_plan)
            guided["goal_plan_after_feedback"] = summarize_goal_plan(baseline_goal_plan)
        feedback_reference = None if planning_feedback is None else {
            "feedback_id": planning_feedback["feedback_id"],
            "path": str(root / "planning-feedback.json"),
            "fingerprint": planning_feedback["feedback_fingerprint"],
        }
        if not interpretation["supported"]:
            artifact = {"contract": CONTRACT, "bootstrap_id": bootstrap_id, "original_input": natural_language, **interpretation, "workspace_root": str(workspace), "target_root": str(target), "constraints": ["controlled_execution", "path_containment", "operator_approval"], "memory_context": context, "memory_context_reference": context.get("context_fingerprint") if context else None, "planning_feedback_reference": feedback_reference, "planning_feedback_fingerprint": planning_feedback.get("feedback_fingerprint") if planning_feedback else None, "planning_feedback_status": planning_feedback_status, "planning_feedback_error": planning_feedback_error, "applied_recommendations": guided["applied_recommendations"], "ignored_recommendations": guided["ignored_recommendations"], "planner_version": planning_feedback.get("planner_version") if planning_feedback else "deterministic-baseline-v1", "goal_plan_before_feedback": guided["goal_plan_before_feedback"], "goal_plan_after_feedback": guided["goal_plan_after_feedback"], "created_at": at, "bootstrap_status": "blocked", "prepare_only": True, "mission_reference": None, "graph_reference": None, "session_reference": None, "manual_review_required": True}
            artifact["artifact_fingerprint"] = fingerprint(artifact); _atomic_json(artifact, artifact_path); return artifact
        from core.runtime.runtime_mission_orchestrator import create_mission
        runtime_workspace = root / "transaction-workspace"
        runtime_workspace.mkdir(parents=True, exist_ok=True)
        mission_path = root / "mission.json"
        operator_scheduler_path = root / "operator-session-scheduler.json"
        mission_scheduler_path = root / "mission-scheduler.json"
        mission_input = {"mission_title": interpretation["normalized_input"][:160], "mission_description": interpretation["normalized_input"], "original_input": natural_language, "normalized_goal": interpretation["normalized_input"], "source": "natural_language_bootstrap", "operator_id": operator_id, "metadata": {"bootstrap_id": bootstrap_id, "interpretation_fingerprint": interpretation["interpretation_fingerprint"], "memory_context": context, "planning_feedback_reference": feedback_reference, "applied_planning_recommendations": guided["applied_recommendations"], "ignored_planning_recommendations": guided["ignored_recommendations"]}}
        mission = create_mission(mission_input, goal_plan=guided["goal_plan"], target_root=target, workspace_root=runtime_workspace, mission_path=mission_path, scheduler_state_path=operator_scheduler_path, now=now)
        first_goal = mission["goal_order"][0]
        from core.runtime.runtime_mission_session import create_mission_session_state, save_mission_session_state
        session_path = root / "mission-session.json"
        session = create_mission_session_state(mission_id=mission["mission_id"], goal_id=first_goal, execution_id=f"mission-execution-{mission['mission_id']}", session_state_path=session_path, mission_state_path=mission_path, goal_graph_state_path=mission_path, execution_registry_state_path=root / "execution-registry.json", scheduler_state_path=mission_scheduler_path, worker_state_path=root / "worker.json", replanning_engine_state_path=root / "replanning.json", daemon_state_path=root / "daemon.json", event_bus_state_path=root / "event-bus.json", target_root=target, workspace_root=runtime_workspace, runtime_config={"bootstrap_id": bootstrap_id}, now=now)
        save_mission_session_state(session, session_path)
        artifact = {"contract": CONTRACT, "bootstrap_id": bootstrap_id, "original_input": natural_language, **interpretation, "workspace_root": str(runtime_workspace), "requested_workspace_root": str(workspace), "target_root": str(target), "constraints": ["controlled_execution", "path_containment", "operator_approval"], "memory_context": context, "memory_context_reference": context.get("context_fingerprint") if context else None, "planning_feedback_reference": feedback_reference, "planning_feedback_fingerprint": planning_feedback.get("feedback_fingerprint") if planning_feedback else None, "planning_feedback_status": planning_feedback_status, "planning_feedback_error": planning_feedback_error, "applied_recommendations": guided["applied_recommendations"], "ignored_recommendations": guided["ignored_recommendations"], "planner_version": planning_feedback.get("planner_version") if planning_feedback else "deterministic-baseline-v1", "goal_plan_before_feedback": guided["goal_plan_before_feedback"], "goal_plan_after_feedback": guided["goal_plan_after_feedback"], "created_at": at, "bootstrap_status": "prepared", "prepare_only": True, "mission_fingerprint": mission["mission_fingerprint"], "mission_reference": {"mission_id": mission["mission_id"], "path": str(mission_path)}, "graph_reference": {"graph_fingerprint": mission["goal_graph"]["graph_fingerprint"], "goal_order": mission["goal_order"], "planning_feedback_reference": feedback_reference}, "session_reference": {"session_id": session["session_id"], "path": str(session_path)}, "artifact_path": str(artifact_path), "manual_review_required": interpretation["manual_review_required"]}
        artifact["artifact_fingerprint"] = fingerprint(artifact); _atomic_json(artifact, artifact_path)
        from core.runtime.runtime_mission_execution_approval_flow import ensure_pending_execution_plan
        plan = ensure_pending_execution_plan(artifact_path, now=now)
        artifact.pop("artifact_fingerprint", None); artifact["execution_plan_reference"] = {"plan_id": plan["plan_id"], "path": str(artifact_path.with_name("execution-plan.json")), "fingerprint": plan["plan_fingerprint"]}; artifact["artifact_fingerprint"] = fingerprint(artifact); _atomic_json(artifact, artifact_path); return artifact

    def run(self, natural_language: str, *, workspace_root: Any, target_root: Any = None, operator_id: str = "zero-mission-cli", memory_context: Mapping[str, Any] | None = None, prepare_only: bool = False, force_new: bool = False, max_iterations: int = 1, now: Any = None) -> dict[str, Any]:
        artifact = self.prepare(natural_language, workspace_root=workspace_root, target_root=target_root, operator_id=operator_id, memory_context=memory_context, force_new=force_new, now=now)
        if prepare_only or artifact["bootstrap_status"] == "blocked": return artifact
        mutation = any(i.get("operation") in {"create_file", "create_directory"} for i in artifact.get("structured_intents") or [])
        if not mutation:
            from core.runtime.runtime_mission_execution_approval_flow import execute_read_only_mission
            closure = execute_read_only_mission(artifact["artifact_path"], max_iterations=max_iterations, now=now)
            value=deepcopy(artifact);value.update(prepare_only=False,bootstrap_status=closure["mission_status"],session_status=closure["mission_status"],approval_required=False,approval_status="not_required",runtime_result=closure);value.pop("artifact_fingerprint",None);value["artifact_fingerprint"]=fingerprint(value);_atomic_json(value,Path(value["artifact_path"]));return value
        from core.runtime.runtime_mission_session import run_mission_session
        session = run_mission_session(artifact["session_reference"]["path"], max_iterations=max_iterations, now=now)
        projected = "waiting_for_plan_confirmation" if mutation and session["session_status"] == "idle" else session["session_status"]
        value = deepcopy(artifact); value.update(prepare_only=False, bootstrap_status=projected, runtime_result=session.get("last_result"), session_status=session["session_status"], approval_required=mutation, approval_status="pending" if mutation else "not_required"); value.pop("artifact_fingerprint", None); value["artifact_fingerprint"] = fingerprint(value); _atomic_json(value, Path(value["artifact_path"])); return value

    def resume(self, session_or_id: str, *, workspace_root: Any, explicit: bool = True, max_iterations: int = 1, now: Any = None) -> dict[str, Any]:
        candidate = Path(session_or_id)
        if candidate.exists(): session_path = candidate.resolve(strict=True)
        else:
            root = Path(workspace_root).resolve(strict=True)
            matches = list(root.rglob("mission-session.json")) + list((root.parent / ".zero_ai_runtime").rglob("mission-session.json")) if (root.parent / ".zero_ai_runtime").exists() else list(root.rglob("mission-session.json"))
            found = []
            from core.runtime.runtime_mission_session import load_mission_session_state
            for item in matches:
                try:
                    if load_mission_session_state(item)["session_id"] == session_or_id: found.append(item)
                except ValueError: continue
            if len(found) != 1: raise ValueError("mission_session_not_found" if not found else "ambiguous_mission_session_id")
            session_path = found[0]
        from core.runtime.runtime_mission_session import resume_mission_session
        return resume_mission_session(session_path, explicit=explicit, max_iterations=max_iterations, now=now)


def bootstrap_mission(natural_language: str, **kwargs: Any) -> dict[str, Any]:
    return NaturalLanguageMissionBootstrap().prepare(natural_language, **kwargs)


def run_natural_language_mission(natural_language: str, **kwargs: Any) -> dict[str, Any]:
    return NaturalLanguageMissionBootstrap().run(natural_language, **kwargs)


__all__ = ["NaturalLanguageMissionBootstrap", "bootstrap_mission", "interpret_natural_language_mission", "normalize_natural_language_mission", "run_natural_language_mission"]
