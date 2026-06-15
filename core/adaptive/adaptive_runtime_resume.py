from __future__ import annotations

import copy
from typing import Any, Mapping

from core.adaptive.adaptive_contract import AdaptiveAction, AdaptiveDecision, AdaptiveRunResult, DeviationReport
from core.adaptive.adaptive_evidence import AdaptiveEvidenceChain
from core.adaptive.adaptive_memory_context import AdaptiveMemoryContextBuilder
from core.adaptive.adaptive_replanner import AdaptiveReplanner
from core.adaptive.deviation_detector import DeviationDetector
from core.adaptive.memory_aware_replanner import MemoryAwareReplanner


class AdaptiveRuntimeResume:
    """Drive adaptive decisions through an existing TaskRunner/TaskRuntime."""

    def __init__(
        self,
        *,
        detector: DeviationDetector | None = None,
        replanner: AdaptiveReplanner | None = None,
        evidence: AdaptiveEvidenceChain | None = None,
        max_cycles: int = 8,
        memory_repository: Any = None,
        adaptive_memory_context_builder: AdaptiveMemoryContextBuilder | None = None,
    ) -> None:
        self.detector = detector or DeviationDetector()
        base_replanner = replanner or AdaptiveReplanner()
        self.replanner = (
            MemoryAwareReplanner(
                base_replanner,
                adaptive_memory_context_builder
                or AdaptiveMemoryContextBuilder(memory_repository),
            )
            if memory_repository is not None or adaptive_memory_context_builder is not None
            else base_replanner
        )
        self.evidence = evidence or AdaptiveEvidenceChain()
        self.max_cycles = max(1, int(max_cycles))

    def run(self, *, task_runner: Any, task: dict[str, Any], current_tick: int = 0) -> dict[str, Any]:
        runtime = task_runner.runtime
        state = runtime.load_runtime_state(task)
        original_steps = copy.deepcopy(state.get("steps", []))
        original_plan_id = str(task.get("plan_id") or task.get("task_id") or task.get("id") or "plan")
        chain = copy.deepcopy(state.get("adaptive_evidence_chain", []))
        counters = copy.deepcopy(state.get("adaptive_counters", {}))
        self.evidence.append(chain, kind="original_plan", payload={"plan_id": original_plan_id, "steps": original_steps})
        state["adaptive_evidence_chain"] = copy.deepcopy(chain)
        state = runtime.begin_terminal_validation(task)
        state["adaptive_evidence_chain"] = copy.deepcopy(chain)
        self._persist(runtime, task, state, chain, counters)
        last_revision = None
        last_report = DeviationReport(str(task.get("task_id") or ""), "", {}, {}, False, "no_deviation")
        last_decision = AdaptiveDecision(AdaptiveAction.CONTINUE, "not_started")
        result: dict[str, Any] = {}

        for cycle in range(self.max_cycles):
            state = runtime.load_runtime_state(task)
            executed_index = int(state.get("current_step_index", 0) or 0)
            result = task_runner.run_task(task, current_tick=current_tick + cycle)
            state = copy.deepcopy(result.get("runtime_state") or runtime.load_runtime_state(task))
            step_result = self._step_result(result)
            step_index = self._executed_step_index(result, executed_index)
            steps = state.get("steps", []) if isinstance(state.get("steps"), list) else []
            step = steps[step_index] if 0 <= step_index < len(steps) and isinstance(steps[step_index], Mapping) else {}

            last_report = self.detector.detect(
                task_id=str(task.get("task_id") or task.get("id") or ""),
                step=step,
                step_result=step_result,
                evidence_refs=[str(chain[-1].get("evidence_id") or "")] if chain else [],
            )
            if not last_report.deviation_detected:
                last_decision = AdaptiveDecision(AdaptiveAction.CONTINUE, "observation_matches_expected")
                self.evidence.append(chain, kind="resume_result", payload=result)
                if str(result.get("status") or "").lower() not in {"needs_observation", "finished", "completed", "success", "done"}:
                    self._persist(runtime, task, state, chain, counters)
                    continue
                observed = task_runner.record_terminal_observation(
                    task,
                    deviation_report=last_report.to_dict(),
                    evidence_persisted=True,
                    current_tick=current_tick + cycle,
                    deviation_step_index=step_index,
                )
                state = copy.deepcopy(observed.get("runtime_state") or runtime.load_runtime_state(task))
                self._persist(runtime, task, state, chain, counters)
                if str(observed.get("status") or "").lower() in {"finished", "completed", "success", "done"}:
                    return self._finish(observed, last_decision, last_report, last_revision, chain)
                continue

            deviation_evidence = self.evidence.append(chain, kind="deviation", payload=last_report.to_dict())
            retry_count = int(counters.get(f"retry:{last_report.step_id}", 0) or 0)
            replan_count = int(counters.get("replan", 0) or 0)
            last_decision = self.replanner.decide(
                last_report,
                step=step,
                retry_count=retry_count,
                replan_count=replan_count,
            )
            self.evidence.append(chain, kind="decision", payload=last_decision.to_dict())

            if last_decision.action is AdaptiveAction.BLOCK:
                self.evidence.append(chain, kind="resume_result", payload={"status": "blocked", "reason": last_decision.reason})
                observed = task_runner.record_terminal_observation(
                    task,
                    deviation_report=last_report.to_dict(),
                    evidence_persisted=True,
                    current_tick=current_tick + cycle,
                    deviation_step_index=step_index,
                    blocked=True,
                )
                state = copy.deepcopy(observed.get("runtime_state") or runtime.load_runtime_state(task))
                state["adaptive_block_reason"] = last_decision.reason
                self._persist(runtime, task, state, chain, counters)
                blocked = copy.deepcopy(result)
                blocked.update({"ok": False, "status": "blocked", "action": "adaptive_blocked", "runtime_state": state})
                return self._finish(blocked, last_decision, last_report, last_revision, chain)

            resume_index = step_index
            if last_decision.action is AdaptiveAction.RETRY:
                counters[f"retry:{last_report.step_id}"] = retry_count + 1
            else:
                counters["replan"] = replan_count + 1
                revised_steps, last_revision = self.replanner.revise(
                    original_plan_id=original_plan_id,
                    steps=steps,
                    failed_step_index=step_index,
                    decision=last_decision,
                )
                state["steps"] = revised_steps
                state["steps_total"] = len(revised_steps)
                self.evidence.append(chain, kind="revised_plan", payload=last_revision.to_dict())
                if last_decision.inserted_steps:
                    resume_index = step_index

            observed = task_runner.record_terminal_observation(
                task,
                deviation_report=last_report.to_dict(),
                evidence_persisted=True,
                current_tick=current_tick + cycle,
                deviation_step_index=resume_index,
            )
            state = copy.deepcopy(observed.get("runtime_state") or runtime.load_runtime_state(task))
            state["last_error"] = None
            state["adaptive_resume_from_step_id"] = last_decision.resume_from_step_id
            state["adaptive_last_deviation_evidence_id"] = deviation_evidence["evidence_id"]
            self._persist(runtime, task, state, chain, counters)

        state = runtime.load_runtime_state(task)
        last_decision = AdaptiveDecision(AdaptiveAction.BLOCK, "adaptive_cycle_limit_exhausted", requires_user_review=True)
        self.evidence.append(chain, kind="decision", payload=last_decision.to_dict())
        state["status"] = "blocked"
        state["adaptive_block_reason"] = last_decision.reason
        self._persist(runtime, task, state, chain, counters)
        result.update({"ok": False, "status": "blocked", "action": "adaptive_blocked", "runtime_state": state})
        return self._finish(result, last_decision, last_report, last_revision, chain)

    @staticmethod
    def _step_result(result: Mapping[str, Any]) -> dict[str, Any]:
        value = result.get("last_result")
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
        return copy.deepcopy(dict(result))

    @staticmethod
    def _executed_step_index(result: Mapping[str, Any], fallback: int) -> int:
        last = result.get("last_result")
        if isinstance(last, Mapping) and last.get("step_index") is not None:
            return int(last.get("step_index") or 0)
        return fallback

    @staticmethod
    def _persist(runtime: Any, task: dict[str, Any], state: dict[str, Any], chain: list[dict[str, Any]], counters: dict[str, Any]) -> None:
        state["adaptive_evidence_chain"] = copy.deepcopy(chain)
        state["adaptive_counters"] = copy.deepcopy(counters)
        saved = runtime.save_runtime_state(task, state)
        sync = getattr(runtime, "_sync_task_from_runtime_state", None)
        if callable(sync):
            sync(task, saved)
        else:
            task["status"] = saved.get("status", task.get("status"))
            task["current_step_index"] = saved.get("current_step_index", task.get("current_step_index", 0))

    @staticmethod
    def _finish(
        result: Mapping[str, Any],
        decision: AdaptiveDecision,
        report: DeviationReport,
        revision: Any,
        chain: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return AdaptiveRunResult(
            ok=bool(result.get("ok")),
            status=str(result.get("status") or ""),
            result=result,
            decision=decision,
            deviation=report,
            revision=revision,
            evidence_chain=tuple(chain),
        ).to_dict()


__all__ = ["AdaptiveRuntimeResume"]
