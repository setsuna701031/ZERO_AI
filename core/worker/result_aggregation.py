from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.worker.worker_contracts import (
    AggregationContract,
    WorkerResult,
    create_aggregation_contract,
    create_final_result,
    ensure_aggregation_contract,
    ensure_final_result_contract,
    ensure_worker_result_contract,
)


class AggregationRuntime:
    """
    Deterministic worker_result aggregation.

    This is not a planner and does not run AI. The caller supplies the merge
    strategy, and this runtime reduces worker_result payloads into final_result.
    """

    def __init__(self, *, contract: AggregationContract | Dict[str, Any] | None = None) -> None:
        if contract is None:
            self.contract = create_aggregation_contract().to_dict()
        elif isinstance(contract, AggregationContract):
            self.contract = contract.to_dict()
        else:
            self.contract = ensure_aggregation_contract(contract)

    def aggregate(self, worker_results: List[WorkerResult | Dict[str, Any]]) -> Dict[str, Any]:
        results = [self._coerce_result(item) for item in worker_results]
        if not results:
            final = create_final_result(
                status="failed",
                summary="no worker results to aggregate",
                result={"items": []},
                aggregation=self._aggregation_meta(results, conflicts=[]),
            )
            return final.to_dict()

        successes = [item for item in results if item["status"] in {"success", "partial"}]
        failures = [item for item in results if item["status"] in {"failed", "blocked"}]
        conflicts = self._detect_artifact_conflicts(results)

        status = self._derive_final_status(successes=successes, failures=failures)
        selected_results = successes if successes else results
        if not successes and self.contract["fallback"] == "partial_success":
            selected_results = results

        strategy = self.contract["strategy"]
        if strategy == "select":
            result_payload, summary = self._select_payload(selected_results)
        elif strategy == "synthesize":
            result_payload, summary = self._synthesize_payload(selected_results, failures)
        else:
            result_payload, summary = self._concat_payload(selected_results)

        artifacts = self._merge_artifacts(results, conflicts)
        trace = self._merge_trace(results, conflicts)
        open_questions = self._merge_open_questions(results, failures, conflicts)
        confidence = self._derive_confidence(successes, failures)

        final = create_final_result(
            status=status,
            summary=summary,
            result=result_payload,
            artifacts=artifacts,
            trace=trace,
            open_questions=open_questions,
            confidence=confidence,
            source_task_ids=[item["task_id"] for item in results],
            aggregation=self._aggregation_meta(results, conflicts=conflicts),
        )
        return final.to_dict()

    def to_display_state(self, final_result: Dict[str, Any]) -> Dict[str, Any]:
        payload = ensure_final_result_contract(final_result)
        return {
            "ok": payload["status"] in {"success", "partial"},
            "display_state_source": "worker_result_aggregation",
            "runtime_status": "done" if payload["status"] in {"success", "partial"} else payload["status"],
            "result_summary": payload["summary"],
            "final_result": copy.deepcopy(payload),
            "source_task_ids": copy.deepcopy(payload["source_task_ids"]),
            "artifacts": copy.deepcopy(payload["artifacts"]),
            "trace": copy.deepcopy(payload["trace"]),
            "open_questions": copy.deepcopy(payload["open_questions"]),
            "aggregation": copy.deepcopy(payload["aggregation"]),
        }

    def _coerce_result(self, worker_result: WorkerResult | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(worker_result, WorkerResult):
            payload = worker_result.to_dict()
        else:
            payload = copy.deepcopy(worker_result)
        return ensure_worker_result_contract(payload)

    def _derive_final_status(
        self,
        *,
        successes: List[Dict[str, Any]],
        failures: List[Dict[str, Any]],
    ) -> str:
        if successes and not failures:
            return "success"
        if successes and failures:
            return "partial" if self.contract["fallback"] == "partial_success" else "failed"
        if failures:
            return "failed"
        return "failed"

    def _concat_payload(self, results: List[Dict[str, Any]]) -> tuple[Dict[str, Any], str]:
        items = []
        summaries = []
        for item in results:
            items.append(
                {
                    "task_id": item["task_id"],
                    "status": item["status"],
                    "summary": item["summary"],
                    "result": copy.deepcopy(item["result"]),
                }
            )
            if item["summary"]:
                summaries.append(f"{item['task_id']}: {item['summary']}")

        return {"strategy": "concat", "items": items}, "\n".join(summaries)

    def _select_payload(self, results: List[Dict[str, Any]]) -> tuple[Dict[str, Any], str]:
        selected = max(
            results,
            key=lambda item: (
                item["status"] == "success",
                float(item.get("confidence") or 0.0),
                item["task_id"],
            ),
        )
        return {
            "strategy": "select",
            "selected_task_id": selected["task_id"],
            "selected_result": copy.deepcopy(selected["result"]),
        }, selected["summary"]

    def _synthesize_payload(
        self,
        successes: List[Dict[str, Any]],
        failures: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        lines = []
        items = []
        for item in successes:
            if item["summary"]:
                lines.append(f"{item['task_id']}: {item['summary']}")
            items.append(
                {
                    "task_id": item["task_id"],
                    "status": item["status"],
                    "result": copy.deepcopy(item["result"]),
                }
            )

        for item in failures:
            lines.append(f"{item['task_id']}: {item['status']}")

        summary = "\n".join(lines)
        return {
            "strategy": "synthesize",
            "synthesis": summary,
            "items": items,
            "failed_task_ids": [item["task_id"] for item in failures],
        }, summary

    def _merge_artifacts(
        self,
        results: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        artifacts = []
        seen_paths = set()
        for item in results:
            for artifact in item.get("artifacts", []):
                if not isinstance(artifact, dict):
                    continue
                path = str(artifact.get("path") or "").strip()
                if self.contract["conflict_handling"] == "prefer_success" and path in seen_paths:
                    continue
                copied = copy.deepcopy(artifact)
                copied.setdefault("task_id", item["task_id"])
                if path:
                    seen_paths.add(path)
                artifacts.append(copied)

        if conflicts and self.contract["conflict_handling"] == "mark_conflict":
            artifacts.append({"kind": "aggregation_conflicts", "conflicts": copy.deepcopy(conflicts)})
        return artifacts

    def _merge_trace(
        self,
        results: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        trace = [
            {
                "event_type": "aggregation_start",
                "strategy": self.contract["strategy"],
                "worker_result_count": len(results),
            }
        ]
        for item in results:
            trace.append(
                {
                    "event_type": "worker_result_collected",
                    "task_id": item["task_id"],
                    "status": item["status"],
                    "confidence": item["confidence"],
                }
            )
            trace.extend(copy.deepcopy(event) for event in item.get("trace", []) if isinstance(event, dict))

        if conflicts:
            trace.append(
                {
                    "event_type": "aggregation_conflict",
                    "conflict_handling": self.contract["conflict_handling"],
                    "conflicts": copy.deepcopy(conflicts),
                }
            )

        trace.append({"event_type": "aggregation_done"})
        return trace

    def _merge_open_questions(
        self,
        results: List[Dict[str, Any]],
        failures: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> List[str]:
        questions = []
        for item in results:
            for question in item.get("open_questions", []):
                if question not in questions:
                    questions.append(question)
        for item in failures:
            message = f"{item['task_id']} ended with {item['status']}"
            if message not in questions:
                questions.append(message)
        if conflicts:
            questions.append("aggregation detected artifact conflicts")
        return questions

    def _derive_confidence(
        self,
        successes: List[Dict[str, Any]],
        failures: List[Dict[str, Any]],
    ) -> float:
        if not successes:
            return 0.0
        score = sum(float(item.get("confidence") or 0.0) for item in successes) / len(successes)
        if failures:
            score *= len(successes) / (len(successes) + len(failures))
        return max(0.0, min(1.0, score))

    def _detect_artifact_conflicts(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_path: Dict[str, List[str]] = {}
        for item in results:
            for artifact in item.get("artifacts", []):
                if not isinstance(artifact, dict):
                    continue
                path = str(artifact.get("path") or "").strip()
                if not path:
                    continue
                by_path.setdefault(path, []).append(item["task_id"])

        return [
            {
                "path": path,
                "task_ids": task_ids,
            }
            for path, task_ids in sorted(by_path.items())
            if len(set(task_ids)) > 1
        ]

    def _aggregation_meta(
        self,
        results: List[Dict[str, Any]],
        *,
        conflicts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "strategy": self.contract["strategy"],
            "conflict_handling": self.contract["conflict_handling"],
            "fallback": self.contract["fallback"],
            "worker_result_count": len(results),
            "success_count": sum(1 for item in results if item.get("status") in {"success", "partial"}),
            "failure_count": sum(1 for item in results if item.get("status") in {"failed", "blocked"}),
            "conflict_count": len(conflicts),
        }
