from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.worker import (
    AggregationRuntime,
    create_aggregation_contract,
    create_worker_result,
    ensure_final_result_contract,
)


PREFIX = "[result-aggregation-strategy-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    summary_result = create_worker_result(
        task_id="manual_worker_summary",
        status="success",
        summary="summary section ready",
        result={"section": "summary", "text": "A concise summary."},
        artifacts=[{"kind": "text", "path": "workspace/worker/summary.txt"}],
        trace=[{"event_type": "worker_done", "task_id": "manual_worker_summary"}],
        confidence=0.9,
    ).to_dict()
    checklist_result = create_worker_result(
        task_id="manual_worker_checklist",
        status="success",
        summary="checklist section ready",
        result={"section": "checklist", "items": ["verify inputs", "merge outputs"]},
        artifacts=[{"kind": "text", "path": "workspace/worker/checklist.txt"}],
        trace=[{"event_type": "worker_done", "task_id": "manual_worker_checklist"}],
        confidence=0.8,
    ).to_dict()

    concat_runtime = AggregationRuntime(
        contract=create_aggregation_contract(
            strategy="concat",
            conflict_handling="preserve_all",
            fallback="partial_success",
        )
    )
    final_result = concat_runtime.aggregate([summary_result, checklist_result])
    try:
        ensure_final_result_contract(final_result)
    except Exception as exc:
        return fail(f"final_result contract failed: {exc}\n{final_result}")

    if final_result.get("status") != "success":
        return fail(f"two successful workers should aggregate as success: {final_result}")
    if final_result.get("source_task_ids") != ["manual_worker_summary", "manual_worker_checklist"]:
        return fail(f"final_result should retain worker source order: {final_result}")
    result_payload = final_result.get("result")
    if not isinstance(result_payload, dict) or len(result_payload.get("items", [])) != 2:
        return fail(f"concat strategy should preserve two result items: {final_result}")
    if len(final_result.get("artifacts", [])) != 2:
        return fail(f"final_result should merge artifacts: {final_result}")
    pass_step("two successful worker_result payloads merge into final_result")

    failed_result = create_worker_result(
        task_id="manual_worker_failed",
        status="failed",
        summary="worker failed while checking appendix",
        result={"error": "appendix missing"},
        artifacts=[],
        trace=[{"event_type": "worker_failed", "task_id": "manual_worker_failed"}],
        confidence=0.0,
    ).to_dict()
    partial_result = concat_runtime.aggregate([summary_result, failed_result])
    if partial_result.get("status") != "partial":
        return fail(f"one success and one failure should use partial_success fallback: {partial_result}")
    if "manual_worker_failed ended with failed" not in partial_result.get("open_questions", []):
        return fail(f"fallback should expose failed worker in open_questions: {partial_result}")
    meta = partial_result.get("aggregation")
    if not isinstance(meta, dict) or meta.get("failure_count") != 1 or meta.get("success_count") != 1:
        return fail(f"aggregation metadata should count success/failure: {partial_result}")
    pass_step("one success plus one failed worker uses fallback correctly")

    display_state = concat_runtime.to_display_state(partial_result)
    if display_state.get("display_state_source") != "worker_result_aggregation":
        return fail(f"display_state should identify aggregation source: {display_state}")
    if display_state.get("final_result") != partial_result:
        return fail(f"display_state should carry final_result: {display_state}")
    if display_state.get("runtime_status") != "done":
        return fail(f"partial final_result should still be displayable as done: {display_state}")
    pass_step("display_state reflects final_result")

    select_runtime = AggregationRuntime(
        contract=create_aggregation_contract(
            strategy="select",
            conflict_handling="prefer_success",
            fallback="partial_success",
        )
    )
    selected = select_runtime.aggregate([summary_result, checklist_result])
    selected_payload = selected.get("result") if isinstance(selected.get("result"), dict) else {}
    if selected_payload.get("selected_task_id") != "manual_worker_summary":
        return fail(f"select strategy should choose highest confidence success: {selected}")
    pass_step("select strategy chooses a deterministic successful result")

    synth_runtime = AggregationRuntime(
        contract=create_aggregation_contract(
            strategy="synthesize",
            conflict_handling="mark_conflict",
            fallback="partial_success",
        )
    )
    conflict_a = create_worker_result(
        task_id="conflict_a",
        status="success",
        summary="first conflict output",
        result={"value": "A"},
        artifacts=[{"kind": "text", "path": "workspace/worker/shared.txt"}],
        confidence=0.7,
    ).to_dict()
    conflict_b = create_worker_result(
        task_id="conflict_b",
        status="success",
        summary="second conflict output",
        result={"value": "B"},
        artifacts=[{"kind": "text", "path": "workspace/worker/shared.txt"}],
        confidence=0.7,
    ).to_dict()
    synthesized = synth_runtime.aggregate([conflict_a, conflict_b])
    synth_meta = synthesized.get("aggregation")
    if not isinstance(synth_meta, dict) or synth_meta.get("conflict_count") != 1:
        return fail(f"synthesize strategy should mark artifact conflict: {synthesized}")
    if "first conflict output" not in synthesized.get("summary", ""):
        return fail(f"synthesize strategy should produce deterministic summary: {synthesized}")
    pass_step("synthesize strategy marks conflicts without AI")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
