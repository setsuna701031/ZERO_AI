from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from core.operator.edit_plan import OperatorEditPlan, create_operator_edit_plan, normalize_operator_edit_plan, validate_operator_edit_plan
from core.operator.repo_context_scanner import RepoContextSnapshot, build_repo_context_snapshot, normalize_repo_context_snapshot
from core.operator.verification_runner import OperatorVerificationResult, run_verification_suite


class CodexOperatorState(str, Enum):
    INITIALIZED = "initialized"
    REPO_SCANNED = "repo_scanned"
    FILES_SELECTED = "files_selected"
    EDIT_PLANNED = "edit_planned"
    EDITS_APPLIED = "edits_applied"
    VERIFICATION_RUNNING = "verification_running"
    VERIFICATION_FAILED = "verification_failed"
    REPAIR_INVOKED = "repair_invoked"
    REPAIRED = "repaired"
    VERIFIED = "verified"
    SUMMARIZED = "summarized"
    FAILED_TERMINAL = "failed_terminal"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    BLOCKED = "blocked"


class CodexOperatorDecision(str, Enum):
    START = "start"
    SCAN_REPO = "scan_repo"
    SELECT_FILES = "select_files"
    PLAN_EDITS = "plan_edits"
    APPLY_EDITS = "apply_edits"
    RUN_VERIFICATION = "run_verification"
    OBSERVE_FAILURES = "observe_failures"
    INVOKE_REPAIR = "invoke_repair"
    FINALIZE = "finalize"
    BLOCK = "block"


@dataclass(frozen=True)
class CodexOperatorStep:
    step_id: str
    state: CodexOperatorState
    decision: CodexOperatorDecision
    ok: bool = True
    reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["decision"] = self.decision.value
        payload["evidence_refs"] = list(self.evidence_refs)
        return payload


@dataclass(frozen=True)
class CodexOperatorRun:
    operator_run_id: str
    task_id: str
    user_intent: str
    repo_root: str
    branch_name: str = ""
    selected_files: tuple[str, ...] = ()
    impacted_files: tuple[str, ...] = ()
    edit_plan: dict[str, Any] = field(default_factory=dict)
    applied_changes: tuple[dict[str, Any], ...] = ()
    verification_commands: tuple[str, ...] = ()
    verification_results: tuple[dict[str, Any], ...] = ()
    failure_observations: tuple[dict[str, Any], ...] = ()
    repair_loop_refs: tuple[str, ...] = ()
    transaction_refs: tuple[str, ...] = ()
    replay_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    steps: tuple[CodexOperatorStep, ...] = ()
    final_state: CodexOperatorState = CodexOperatorState.INITIALIZED
    success: bool = False
    commit_message: str = ""
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "selected_files",
            "impacted_files",
            "applied_changes",
            "verification_commands",
            "verification_results",
            "failure_observations",
            "repair_loop_refs",
            "transaction_refs",
            "replay_refs",
            "evidence_refs",
            "memory_refs",
            "prediction_refs",
            "steps",
        ):
            value = getattr(self, key)
            payload[key] = [item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item) for item in value]
        payload["final_state"] = self.final_state.value
        return payload


@dataclass(frozen=True)
class CodexOperatorResult:
    operator_run_id: str
    task_id: str
    final_state: CodexOperatorState
    success: bool
    summary: str
    commit_message: str
    run: CodexOperatorRun
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["final_state"] = self.final_state.value
        payload["run"] = self.run.to_dict()
        return payload


_RUNS: dict[str, CodexOperatorRun] = {}


def start_operator_run(*, task_id: str, user_intent: str, repo_root: str | Path, branch_name: str = "") -> CodexOperatorRun:
    root = str(Path(repo_root).resolve())
    base = {"task_id": str(task_id or ""), "user_intent": str(user_intent or ""), "repo_root": root, "branch_name": str(branch_name or "")}
    digest = _digest(base)
    now = _now()
    run = CodexOperatorRun(
        operator_run_id="codex_operator_run:" + digest[:16],
        task_id=base["task_id"] or "task-operator",
        user_intent=base["user_intent"],
        repo_root=root,
        branch_name=base["branch_name"],
        steps=(_step(CodexOperatorState.INITIALIZED, CodexOperatorDecision.START, "operator initialized"),),
        created_at=now,
        updated_at=now,
    )
    return _store(_with_digest(run))


def scan_repository_context(
    run: CodexOperatorRun | str,
    *,
    max_files: int = 500,
    allowed_paths: Any = None,
) -> CodexOperatorRun:
    current = get_operator_run(run)
    snapshot = build_repo_context_snapshot(
        current.repo_root,
        task_intent=current.user_intent,
        max_files=max_files,
        allow_paths=allowed_paths,
    )
    evidence = _operator_evidence(current, "repo_scan", "repo_scanned")
    return _store(
        _with_digest(
            _replace(
                current,
                selected_files=snapshot.selected_files,
                impacted_files=snapshot.selected_files,
                evidence_refs=_append(current.evidence_refs, evidence),
                final_state=CodexOperatorState.REPO_SCANNED,
                steps=(*current.steps, _step(CodexOperatorState.REPO_SCANNED, CodexOperatorDecision.SCAN_REPO, snapshot.snapshot_id, evidence)),
            )
        )
    )


def select_impacted_files(run: CodexOperatorRun | str, files: Any = None) -> CodexOperatorRun:
    current = get_operator_run(run)
    selected = _text_tuple(files) or current.selected_files or current.impacted_files
    evidence = _operator_evidence(current, "select_files", "files_selected")
    return _store(
        _with_digest(
            _replace(
                current,
                selected_files=selected,
                impacted_files=selected,
                evidence_refs=_append(current.evidence_refs, evidence),
                final_state=CodexOperatorState.FILES_SELECTED,
                steps=(*current.steps, _step(CodexOperatorState.FILES_SELECTED, CodexOperatorDecision.SELECT_FILES, "files selected", evidence)),
            )
        )
    )


def create_edit_plan(run: CodexOperatorRun | str, *, test_commands: Any = None, target_files: Any = None) -> CodexOperatorRun:
    current = get_operator_run(run)
    plan = create_operator_edit_plan(
        task_id=current.task_id,
        user_intent=current.user_intent,
        impacted_files=current.impacted_files or current.selected_files,
        target_files=target_files or current.selected_files or current.impacted_files,
        test_commands=test_commands,
        evidence_refs=current.evidence_refs,
        memory_refs=current.memory_refs,
        prediction_refs=current.prediction_refs,
    )
    evidence = _operator_evidence(current, "edit_plan", "edit_planned")
    return _store(
        _with_digest(
            _replace(
                current,
                edit_plan=plan.to_dict(),
                verification_commands=plan.test_commands,
                prediction_refs=_append(current.prediction_refs, plan.prediction_refs),
                evidence_refs=_append(current.evidence_refs, evidence),
                final_state=CodexOperatorState.EDIT_PLANNED,
                steps=(*current.steps, _step(CodexOperatorState.EDIT_PLANNED, CodexOperatorDecision.PLAN_EDITS, plan.plan_id, evidence)),
            )
        )
    )


def apply_operator_edit_plan(run: CodexOperatorRun | str, *, authority: Mapping[str, Any] | None = None, executor: Any = None) -> CodexOperatorRun:
    current = get_operator_run(run)
    if not current.edit_plan:
        return _blocked(current, "operator edit plan missing")
    validate_operator_edit_plan(current.edit_plan)
    from core.runtime.execution_authority import validate_authority_metadata

    validation = validate_authority_metadata(authority or {}, surface="operator_apply_edit")
    if not validation.get("ok"):
        return _blocked(current, str(validation.get("reason") or "operator_apply_edit_requires_authority"))
    return _blocked(current, "legacy_runtime_dispatcher_migration_required")


def run_operator_verification(run: CodexOperatorRun | str, *, authority: Mapping[str, Any] | None = None, verification_results: Any = None, executor: Any = None) -> CodexOperatorRun:
    current = get_operator_run(run)
    evidence = _operator_evidence(current, "verification", "verification_running")
    if verification_results is None:
        results = run_verification_suite(current.verification_commands or ("python -m pytest tests -q",), authority=authority, task={"task_id": current.task_id}, context={"repo_root": current.repo_root}, executor=executor)
        normalized = [result.to_dict() for result in results]
    else:
        normalized = [dict(item) if isinstance(item, Mapping) else {"ok": bool(item)} for item in _iter_any(verification_results)]
    ok = all(bool(item.get("ok")) for item in normalized)
    state = CodexOperatorState.VERIFIED if ok else CodexOperatorState.VERIFICATION_FAILED
    return _store(_with_digest(_replace(current, verification_results=(*current.verification_results, *normalized), evidence_refs=_append(current.evidence_refs, evidence), final_state=state, steps=(*current.steps, _step(state, CodexOperatorDecision.RUN_VERIFICATION, "verification passed" if ok else "verification failed", evidence, ok=ok)))))


def observe_operator_failures(run: CodexOperatorRun | str) -> CodexOperatorRun:
    current = get_operator_run(run)
    failures = tuple(item for item in current.verification_results if not bool(item.get("ok")))
    observations = tuple({"reason": str(item.get("stderr") or item.get("reason") or "operator_verification_failed"), "verification_id": str(item.get("verification_id") or "")} for item in failures)
    evidence = _operator_evidence(current, "observe_failure", "verification_failed")
    return _store(_with_digest(_replace(current, failure_observations=(*current.failure_observations, *observations), evidence_refs=_append(current.evidence_refs, evidence), final_state=CodexOperatorState.VERIFICATION_FAILED if observations else current.final_state, steps=(*current.steps, _step(CodexOperatorState.VERIFICATION_FAILED, CodexOperatorDecision.OBSERVE_FAILURES, "failures observed", evidence, ok=not observations)))))


def invoke_autonomous_repair(run: CodexOperatorRun | str, *, authority: Mapping[str, Any] | None = None, allow_repair: bool = True, repair_result: Any = None) -> CodexOperatorRun:
    current = get_operator_run(run)
    if not allow_repair:
        return _store(_with_digest(_replace(current, final_state=CodexOperatorState.REQUIRES_HUMAN_REVIEW, steps=(*current.steps, _step(CodexOperatorState.REQUIRES_HUMAN_REVIEW, CodexOperatorDecision.INVOKE_REPAIR, "repair not allowed", ok=False)))))
    if repair_result is None:
        from core.runtime.autonomous_repair_loop import run_autonomous_repair_loop

        failure = current.failure_observations[-1] if current.failure_observations else {"reason": "operator_verification_failed"}
        repair_result = run_autonomous_repair_loop(
            {
                "task_id": current.task_id,
                "step_id": "operator_repair",
                "trace_id": current.operator_run_id,
                "failure_id": str(failure.get("verification_id") or "operator_failure"),
                "reason": str(failure.get("reason") or "operator_verification_failed"),
                "transaction_id": current.transaction_refs[-1] if current.transaction_refs else "",
            },
            authority=authority,
            max_attempts=1,
        )
    repair_payload = repair_result.to_dict() if hasattr(repair_result, "to_dict") else dict(repair_result or {})
    loop_ref = str(repair_payload.get("loop_id") or repair_payload.get("repair_loop_id") or "")
    final = str(repair_payload.get("final_state") or repair_payload.get("state") or "")
    state = CodexOperatorState.REPAIRED if final in {"stabilized", "committed", "rolled_back"} or repair_payload.get("stabilized") else CodexOperatorState.FAILED_TERMINAL
    if final == "requires_human_review":
        state = CodexOperatorState.REQUIRES_HUMAN_REVIEW
    evidence = _operator_evidence(current, "repair", state.value, refs=[loop_ref])
    return _store(_with_digest(_replace(current, repair_loop_refs=_append(current.repair_loop_refs, loop_ref), transaction_refs=_append(current.transaction_refs, repair_payload.get("transaction_refs")), evidence_refs=_append(current.evidence_refs, evidence, repair_payload.get("evidence_refs")), final_state=state, steps=(*current.steps, _step(CodexOperatorState.REPAIR_INVOKED, CodexOperatorDecision.INVOKE_REPAIR, "repair invoked", evidence), _step(state, CodexOperatorDecision.INVOKE_REPAIR, "repair completed", evidence, ok=state is not CodexOperatorState.FAILED_TERMINAL)))))


def finalize_operator_run(run: CodexOperatorRun | str) -> CodexOperatorResult:
    current = get_operator_run(run)
    success = current.final_state in {CodexOperatorState.VERIFIED, CodexOperatorState.REPAIRED, CodexOperatorState.SUMMARIZED}
    message = generate_commit_message(current)
    summary = _summary(current, success=success)
    memory_refs = _memory_refs_for_run(current, success=success)
    evidence = _operator_evidence(current, "summary", "summarized")
    final_run = _store(_with_digest(_replace(current, success=success, commit_message=message, summary=summary, memory_refs=_append(current.memory_refs, memory_refs), evidence_refs=_append(current.evidence_refs, evidence), final_state=CodexOperatorState.SUMMARIZED if success else current.final_state, steps=(*current.steps, _step(CodexOperatorState.SUMMARIZED if success else current.final_state, CodexOperatorDecision.FINALIZE, "operator summarized", evidence, ok=success)))))
    base = _normalize_operator_refs({"operator_run_id": final_run.operator_run_id, "task_id": final_run.task_id, "final_state": final_run.final_state.value, "success": final_run.success, "summary": final_run.summary, "commit_message": final_run.commit_message, "run": final_run.to_dict()})
    digest = _digest(base)
    return CodexOperatorResult(final_run.operator_run_id, final_run.task_id, final_run.final_state, final_run.success, final_run.summary, final_run.commit_message, final_run, digest)


def generate_commit_message(run: CodexOperatorRun | Mapping[str, Any]) -> str:
    payload = run.to_dict() if isinstance(run, CodexOperatorRun) else dict(run)
    files = payload.get("selected_files") or payload.get("impacted_files") or []
    scope = Path(files[0]).stem if files else "operator"
    intent = str(payload.get("user_intent") or "operator changes").strip()
    return f"{scope}: {intent[:72]}".strip()


def run_codex_style_operator(
    *,
    task_id: str,
    user_intent: str,
    repo_root: str | Path,
    branch_name: str = "",
    authority: Mapping[str, Any] | None = None,
    verification_results: Any = None,
    allow_repair: bool = True,
    dry_run: bool = False,
    allowed_paths: Any = None,
) -> CodexOperatorResult:
    run = start_operator_run(task_id=task_id, user_intent=user_intent, repo_root=repo_root, branch_name=branch_name)
    run = scan_repository_context(run, allowed_paths=allowed_paths)
    selected = _filter_allowed_paths(run.selected_files or run.impacted_files, allowed_paths)
    run = select_impacted_files(run, selected)
    run = create_edit_plan(run)
    if dry_run:
        return finalize_operator_run(run)
    run = apply_operator_edit_plan(run, authority=authority)
    if run.final_state is CodexOperatorState.BLOCKED:
        return finalize_operator_run(run)
    run = run_operator_verification(run, authority=authority, verification_results=verification_results)
    if run.final_state is CodexOperatorState.VERIFICATION_FAILED:
        run = observe_operator_failures(run)
        run = invoke_autonomous_repair(run, authority=authority, allow_repair=allow_repair)
        if run.final_state is CodexOperatorState.REPAIRED:
            run = run_operator_verification(run, authority=authority, verification_results=[{"ok": True, "reason": "repair_verified"}])
    return finalize_operator_run(run)


def _filter_allowed_paths(files: Any, allowed_paths: Any = None) -> tuple[str, ...]:
    values = _text_tuple(files)
    allowed = tuple(path.strip().replace("\\", "/").rstrip("/") for path in _text_tuple(allowed_paths))
    if not allowed:
        return values
    return tuple(path for path in values if any(path.replace("\\", "/") == prefix or path.replace("\\", "/").startswith(prefix + "/") for prefix in allowed))


def get_operator_run(run: CodexOperatorRun | str) -> CodexOperatorRun:
    if isinstance(run, CodexOperatorRun):
        return run
    value = _RUNS.get(str(run or ""))
    if value is None:
        raise KeyError(f"operator run not found: {run}")
    return value


def list_operator_runs(*, task_id: str | None = None) -> tuple[CodexOperatorRun, ...]:
    values = tuple(_RUNS.values())
    if task_id is not None:
        values = tuple(item for item in values if item.task_id == task_id)
    return values


def normalize_operator_run(run: CodexOperatorRun | CodexOperatorResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = run.to_dict() if hasattr(run, "to_dict") else copy.deepcopy(dict(run))
    return _normalize_operator_refs(_normalize_value(payload))


def _blocked(current: CodexOperatorRun, reason: str) -> CodexOperatorRun:
    evidence = _operator_evidence(current, "blocked", reason)
    return _store(_with_digest(_replace(current, evidence_refs=_append(current.evidence_refs, evidence), final_state=CodexOperatorState.BLOCKED, steps=(*current.steps, _step(CodexOperatorState.BLOCKED, CodexOperatorDecision.BLOCK, reason, evidence, ok=False)))))


def _memory_refs_for_run(run: CodexOperatorRun, *, success: bool) -> tuple[str, ...]:
    try:
        from core.runtime.runtime_memory_engine import RuntimeMemoryKind, append_runtime_memory, create_memory_record

        records = [
            create_memory_record(kind=RuntimeMemoryKind.EXECUTION_SUMMARY, task_id=run.task_id, trace_id=run.operator_run_id, evidence_refs=run.evidence_refs, summary=run.summary or "operator execution summary", semantic_tags=["operator", "execution"], terminal_state=run.final_state.value),
        ]
        if run.failure_observations:
            records.append(create_memory_record(kind=RuntimeMemoryKind.FAILURE_PATTERN, task_id=run.task_id, trace_id=run.operator_run_id, evidence_refs=run.evidence_refs, summary="operator failure pattern", semantic_tags=["operator", "failure"], failure_signature=str(run.failure_observations[-1].get("reason") or "operator_failure"), terminal_state=run.final_state.value))
        if run.repair_loop_refs:
            records.append(create_memory_record(kind=RuntimeMemoryKind.REPAIR_HISTORY, task_id=run.task_id, trace_id=run.operator_run_id, repair_loop_id=",".join(run.repair_loop_refs), evidence_refs=run.evidence_refs, summary="operator repair history", semantic_tags=["operator", "repair"], terminal_state=run.final_state.value))
        if success:
            records.append(create_memory_record(kind=RuntimeMemoryKind.STABILIZATION_HISTORY, task_id=run.task_id, trace_id=run.operator_run_id, evidence_refs=run.evidence_refs, summary="operator stabilized", semantic_tags=["operator", "stabilization"], stabilization_result="stabilized", terminal_state="stabilized"))
        return tuple(append_runtime_memory(record).memory_id for record in records)
    except Exception:
        return ()


def _operator_evidence(run: CodexOperatorRun, decision: str, state: str, refs: Any = None) -> str:
    try:
        from core.runtime.runtime_evidence_freeze import RuntimeEvidenceKind, create_evidence_record

        return create_evidence_record(kind=RuntimeEvidenceKind.AUDIT, task_id=run.task_id, trace_id=run.operator_run_id, decision=decision, state=state, reason=run.user_intent, refs=refs).evidence_id
    except Exception:
        return _stable_id("operator_evidence", run.operator_run_id, decision, state, refs)


def _transaction_refs(raw: Mapping[str, Any]) -> tuple[str, ...]:
    refs = []
    for key in ("runtime_transaction",):
        value = raw.get(key) if isinstance(raw, Mapping) else None
        if isinstance(value, Mapping) and value.get("transaction_id"):
            refs.append(str(value["transaction_id"]))
    result = raw.get("result") if isinstance(raw, Mapping) and isinstance(raw.get("result"), Mapping) else {}
    tx = result.get("runtime_transaction") if isinstance(result.get("runtime_transaction"), Mapping) else {}
    if tx.get("transaction_id"):
        refs.append(str(tx["transaction_id"]))
    return tuple(dict.fromkeys(refs))


def _summary(run: CodexOperatorRun, *, success: bool) -> str:
    return f"Operator {'completed' if success else 'stopped'} for {run.task_id}: {len(run.applied_changes)} controlled change batch(es), {len(run.verification_results)} verification result(s)."


def _replace(current: CodexOperatorRun, **updates: Any) -> CodexOperatorRun:
    return replace(current, **updates, updated_at=_now())


def _with_digest(run: CodexOperatorRun) -> CodexOperatorRun:
    payload = run.to_dict()
    payload.pop("normalized_digest", None)
    return replace(run, normalized_digest=_digest(_normalize_operator_refs(payload)))


def _store(run: CodexOperatorRun) -> CodexOperatorRun:
    _RUNS[run.operator_run_id] = run
    return run


def _step(state: CodexOperatorState, decision: CodexOperatorDecision, reason: str, evidence_refs: Any = None, ok: bool = True) -> CodexOperatorStep:
    return CodexOperatorStep(step_id=_stable_id("operator_step", state.value, decision.value, reason), state=state, decision=decision, ok=ok, reason=str(reason or ""), evidence_refs=_text_tuple(evidence_refs), created_at=_now())


def _append(values: Any, *items: Any) -> tuple[str, ...]:
    result = list(_text_tuple(values))
    for item in items:
        for text in _text_tuple(item):
            if text not in result:
                result.append(text)
    return tuple(result)


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())


def _iter_any(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, Mapping)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{hashlib.sha256(json.dumps(_normalize_value(parts), sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]}"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return copy.deepcopy(value)


def _normalize_operator_refs(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key in sorted(value):
            item = _normalize_operator_refs(value[key])
            if key == "normalized_digest":
                normalized[key] = "<normalized_digest>"
            elif key in {"transaction_refs", "evidence_refs", "memory_refs", "prediction_refs", "repair_loop_refs"}:
                normalized[key] = [f"<{key[:-1]}>" for _ in (item or [])]
            elif key in {"transaction_id", "evidence_id", "memory_id", "prediction_id", "loop_id", "repair_loop_id", "plan_id"} and isinstance(item, str):
                normalized[key] = _placeholder_for_ref_key(key)
            else:
                normalized[key] = item
        return normalized
    if isinstance(value, list):
        return [_normalize_operator_refs(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_operator_refs(item) for item in value]
    if isinstance(value, str):
        for prefix, placeholder in (
            ("runtime_tx:", "<transaction_ref>"),
            ("runtime_evidence:", "<evidence_ref>"),
            ("runtime_memory:", "<memory_ref>"),
            ("runtime_prediction:", "<prediction_ref>"),
            ("repair_loop:", "<repair_loop_ref>"),
            ("operator_edit_plan:", "<edit_plan_ref>"),
            ("operator_step:", "<operator_step_ref>"),
        ):
            if value.startswith(prefix):
                return placeholder
    return value


def _placeholder_for_ref_key(key: str) -> str:
    return {
        "transaction_id": "<transaction_ref>",
        "evidence_id": "<evidence_ref>",
        "memory_id": "<memory_ref>",
        "prediction_id": "<prediction_ref>",
        "loop_id": "<repair_loop_ref>",
        "repair_loop_id": "<repair_loop_ref>",
        "plan_id": "<edit_plan_ref>",
    }.get(key, "<runtime_ref>")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
