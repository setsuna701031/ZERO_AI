from __future__ import annotations

import inspect
import pprint
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_step_executor(workspace_root: Path) -> Any:
    from core.runtime.step_executor import StepExecutor

    signature = inspect.signature(StepExecutor)
    kwargs: Dict[str, Any] = {}

    if "workspace_root" in signature.parameters:
        kwargs["workspace_root"] = workspace_root
    if "workspace_dir" in signature.parameters:
        kwargs["workspace_dir"] = workspace_root
    if "runtime_store" in signature.parameters:
        kwargs["runtime_store"] = None
    if "tool_registry" in signature.parameters:
        kwargs["tool_registry"] = None
    if "llm_client" in signature.parameters:
        kwargs["llm_client"] = None
    if "debug" in signature.parameters:
        kwargs["debug"] = False

    return StepExecutor(**kwargs)


def _execute_step(
    executor: Any,
    step: Dict[str, Any],
    *,
    step_index: int | None = None,
    step_count: int | None = None,
) -> Dict[str, Any]:
    if hasattr(executor, "execute_step"):
        method = executor.execute_step
    elif hasattr(executor, "run_step"):
        method = executor.run_step
    else:
        raise AssertionError("StepExecutor has no execute_step/run_step method")

    attempts = [
        lambda: method(step, step_index=step_index, step_count=step_count),
        lambda: method(step=step, step_index=step_index, step_count=step_count),
        lambda: method(step),
        lambda: method(step=step),
    ]

    last_error: TypeError | None = None
    for call in attempts:
        try:
            result = call()
            if not isinstance(result, dict):
                raise AssertionError(f"execute_step returned non-dict result: {type(result)!r}")
            return result
        except TypeError as exc:
            last_error = exc

    raise AssertionError(f"Unable to call StepExecutor step method: {last_error}")


def _execute_steps(executor: Any, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not hasattr(executor, "execute_steps"):
        raise AssertionError("StepExecutor has no execute_steps method")

    method = executor.execute_steps
    attempts = [
        lambda: method(steps),
        lambda: method(steps=steps),
    ]

    last_error: TypeError | None = None
    for call in attempts:
        try:
            result = call()
            if not isinstance(result, dict):
                raise AssertionError(f"execute_steps returned non-dict result: {type(result)!r}")
            return result
        except TypeError as exc:
            last_error = exc

    raise AssertionError(f"Unable to call StepExecutor.execute_steps: {last_error}")


def _list_handlers(executor: Any) -> List[str]:
    if hasattr(executor, "list_handlers"):
        return sorted(str(x) for x in executor.list_handlers())
    if hasattr(executor, "handlers"):
        handlers = getattr(executor, "handlers", {})
        if isinstance(handlers, dict):
            return sorted(str(x) for x in handlers.keys())
    return []


def _print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def _assert_trace_entry(
    entry: Dict[str, Any],
    *,
    step_type: str,
    step_index: int,
    ok: bool,
    message: str,
    error_type: str | None,
) -> None:
    assert entry.get("step_type") == step_type
    assert entry.get("runtime_mode") == "execute"
    assert entry.get("step_index") == step_index
    assert entry.get("ok") is ok
    assert entry.get("message") == message
    assert entry.get("final_answer") == message
    assert entry.get("error_type") == error_type
    assert entry.get("classification") is None
    assert entry.get("attempts") == 1
    assert entry.get("max_attempts") == 1
    assert entry.get("retry_used") is False


def _assert_unsupported_step_contract(result: Dict[str, Any]) -> None:
    assert result.get("ok") is False
    assert result.get("step_type") == "not_real_step"
    assert result.get("runtime_mode") == "execute"
    assert result.get("message") == "unsupported step type: not_real_step"
    assert result.get("final_answer") == "unsupported step type: not_real_step"

    error = result.get("error")
    assert isinstance(error, dict)
    assert error.get("type") == "unsupported_step_type"
    assert error.get("message") == "unsupported step type: not_real_step"
    assert error.get("retryable") is False

    trace = result.get("execution_trace")
    assert isinstance(trace, list)
    assert len(trace) >= 1

    _assert_trace_entry(
        trace[0],
        step_type="not_real_step",
        step_index=result.get("step_index", 1),
        ok=False,
        message="unsupported step type: not_real_step",
        error_type="unsupported_step_type",
    )


def _assert_execute_steps_failure_contract(result: Dict[str, Any]) -> None:
    assert result.get("ok") is False
    assert result.get("summary") == "step execution failed"
    assert result.get("message") == "unsupported step type: not_real_step"
    assert result.get("final_answer") == "unsupported step type: not_real_step"
    assert result.get("step_count") == 2
    assert result.get("completed_steps") == 0
    assert result.get("failed_step") == 0

    results = result.get("results")
    assert isinstance(results, list)
    assert len(results) == 1
    _assert_unsupported_step_contract(results[0])
    assert results[0].get("step_index") == 1
    assert results[0].get("step_count") == 2

    last_result = result.get("last_result")
    assert isinstance(last_result, dict)
    assert last_result.get("step_type") == "not_real_step"

    error = result.get("error")
    assert isinstance(error, dict)
    assert error.get("type") == "unsupported_step_type"
    assert error.get("retryable") is False

    trace = result.get("execution_trace")
    assert isinstance(trace, list)
    assert len(trace) >= 1
    assert trace[0].get("step_index") == 1
    assert trace[0].get("error_type") == "unsupported_step_type"


def _assert_execute_steps_empty_contract(result: Dict[str, Any]) -> None:
    assert result == {
        "ok": True,
        "summary": "all steps executed",
        "message": "執行完成",
        "final_answer": "執行完成",
        "step_count": 0,
        "completed_steps": 0,
        "failed_step": None,
        "results": [],
        "last_result": None,
        "error": None,
        "execution_trace": [],
    }


def _assert_success_step_result(
    result: Dict[str, Any],
    *,
    step_type: str,
    step_index: int,
    step_count: int,
    expected_content: str,
) -> None:
    assert result.get("ok") is True
    assert result.get("runtime_mode") == "execute"
    assert result.get("step_type") == step_type
    assert result.get("step_index") == step_index
    assert result.get("step_count") == step_count
    assert result.get("message") == expected_content
    assert result.get("final_answer") == expected_content
    assert result.get("error") is None
    assert result.get("task_id") is None

    step = result.get("step")
    assert isinstance(step, dict)
    assert step.get("type") == step_type
    assert step.get("path") == "workspace/shared/contract_ok.txt"

    inner = result.get("result")
    assert isinstance(inner, dict)
    assert inner.get("ok") is True
    assert inner.get("runtime_mode") == "execute"
    assert inner.get("content") == expected_content
    assert inner.get("error") is None

    inner_result = inner.get("result")
    assert isinstance(inner_result, dict)
    assert inner_result.get("type") == step_type
    assert inner_result.get("path") == "workspace/shared/contract_ok.txt"
    assert inner_result.get("content") == expected_content

    if step_type == "write_file":
        assert inner_result.get("scope") == "sandbox"
        assert inner_result.get("bytes") == len(expected_content.encode("utf-8"))
    elif step_type == "read_file":
        assert isinstance(inner_result.get("candidates"), list)
        assert inner_result.get("full_path")
    elif step_type == "verify":
        assert inner_result.get("actual") is True
        assert inner_result.get("expected") == expected_content
        assert inner_result.get("mode") == "contains"
        assert isinstance(inner_result.get("candidates"), list)
        assert inner_result.get("full_path")

    trace = result.get("execution_trace")
    assert isinstance(trace, list)
    assert len(trace) >= 1
    _assert_trace_entry(
        trace[0],
        step_type=step_type,
        step_index=step_index,
        ok=True,
        message=expected_content,
        error_type=None,
    )


def _assert_execute_steps_success_contract(result: Dict[str, Any]) -> None:
    assert result.get("ok") is True
    assert result.get("summary") == "all steps executed"
    assert result.get("message") == "CONTRACT_OK"
    assert result.get("final_answer") == "CONTRACT_OK"
    assert result.get("step_count") == 3
    assert result.get("completed_steps") == 3
    assert result.get("failed_step") is None
    assert result.get("error") is None

    results = result.get("results")
    assert isinstance(results, list)
    assert len(results) == 3

    _assert_success_step_result(
        results[0],
        step_type="write_file",
        step_index=1,
        step_count=3,
        expected_content="CONTRACT_OK",
    )
    _assert_success_step_result(
        results[1],
        step_type="read_file",
        step_index=2,
        step_count=3,
        expected_content="CONTRACT_OK",
    )
    _assert_success_step_result(
        results[2],
        step_type="verify",
        step_index=3,
        step_count=3,
        expected_content="CONTRACT_OK",
    )

    last_result = result.get("last_result")
    assert isinstance(last_result, dict)
    assert last_result.get("step_type") == "verify"
    assert last_result.get("message") == "CONTRACT_OK"
    assert last_result.get("final_answer") == "CONTRACT_OK"

    trace = result.get("execution_trace")
    assert isinstance(trace, list)
    assert len(trace) == 3
    for expected_index, expected_type in enumerate(["write_file", "read_file", "verify"], start=1):
        _assert_trace_entry(
            trace[expected_index - 1],
            step_type=expected_type,
            step_index=expected_index,
            ok=True,
            message="CONTRACT_OK",
            error_type=None,
        )


def main() -> int:
    print("[StepExecutor Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    with tempfile.TemporaryDirectory() as tmp:
        executor = _make_step_executor(Path(tmp))

        _print_section("1. list_handlers")
        handlers = _list_handlers(executor)
        pprint.pprint(handlers)

        assert "apply_patch" in handlers
        assert "verify" in handlers
        assert "read_file" in handlers
        assert "write_file" in handlers

        _print_section("2. unsupported step type")
        unsupported_result = _execute_step(executor, {"type": "not_real_step"})
        pprint.pprint(unsupported_result)
        _assert_unsupported_step_contract(unsupported_result)

        _print_section("3. execute_steps fail")
        failed_batch_result = _execute_steps(
            executor,
            [
                {"type": "not_real_step"},
                {"type": "noop", "message": "should not run after unsupported step"},
            ],
        )
        pprint.pprint(failed_batch_result)
        _assert_execute_steps_failure_contract(failed_batch_result)

        _print_section("4. execute_steps empty")
        empty_result = _execute_steps(executor, [])
        pprint.pprint(empty_result)
        _assert_execute_steps_empty_contract(empty_result)

        _print_section("5. execute_steps write/read/verify success")
        success_result = _execute_steps(
            executor,
            [
                {
                    "type": "write_file",
                    "path": "workspace/shared/contract_ok.txt",
                    "content": "CONTRACT_OK",
                },
                {
                    "type": "read_file",
                    "path": "workspace/shared/contract_ok.txt",
                },
                {
                    "type": "verify",
                    "path": "workspace/shared/contract_ok.txt",
                    "contains": "CONTRACT_OK",
                },
            ],
        )
        pprint.pprint(success_result)
        _assert_execute_steps_success_contract(success_result)

    _print_section("驗收結論")
    print("1. StepExecutor 可正常建立")
    print("2. unsupported step type 會回固定錯誤格式")
    print("3. execute_steps 失敗批次格式固定")
    print("4. execute_steps 空批次格式固定")
    print("5. write/read/verify 成功批次格式固定")
    print()
    print("PASS: test_step_executor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
