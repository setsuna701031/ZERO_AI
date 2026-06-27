from core.tasks.scheduler_core.repo_runtime_adapter import (
    repo_runtime_adapter_error_text,
    repo_runtime_adapter_error_type,
    repo_runtime_adapter_execution_trace,
    repo_runtime_adapter_final_answer,
    repo_runtime_adapter_last_result,
    repo_runtime_adapter_message,
    repo_runtime_adapter_ok,
    repo_runtime_adapter_runtime_mode,
)


def test_repo_runtime_adapter_ok_from_status_and_errors() -> None:
    assert repo_runtime_adapter_ok({"status": "finished"}) is True
    assert repo_runtime_adapter_ok({"status": "failed"}) is False
    assert repo_runtime_adapter_ok({"last_error": "boom"}) is False
    assert repo_runtime_adapter_ok({"ok": False, "status": "finished"}) is False


def test_repo_runtime_adapter_message_and_final_answer() -> None:
    assert repo_runtime_adapter_message({"message": "hello"}, ok=True) == "hello"
    assert repo_runtime_adapter_message({"failure_message": "boom"}, ok=False) == "boom"
    assert repo_runtime_adapter_message({}, ok=True) == "runtime state ok"
    assert repo_runtime_adapter_message({}, ok=False) == "runtime state failed"
    assert repo_runtime_adapter_final_answer({"final_answer": "done"}, message="fallback") == "done"
    assert repo_runtime_adapter_final_answer({}, message="fallback") == "fallback"


def test_repo_runtime_adapter_error_text_and_type() -> None:
    assert repo_runtime_adapter_error_text({"error": {"message": "nested"}}) == "nested"
    assert repo_runtime_adapter_error_text({"error_text": "flat"}) == "flat"
    assert repo_runtime_adapter_error_type({"failure_type": "custom"}) == "custom"
    assert repo_runtime_adapter_error_type({"error": {"code": "E_FAIL"}}) == "E_FAIL"
    assert repo_runtime_adapter_error_type({"error_text": "boom"}) == "runtime_state_failed"
    assert repo_runtime_adapter_error_type({}) == ""


def test_repo_runtime_adapter_runtime_mode_last_result_and_trace_are_copied() -> None:
    assert repo_runtime_adapter_runtime_mode({"execution_mode": "native"}) == "native"
    assert repo_runtime_adapter_runtime_mode({}) == "repo_state"

    source = {"last_result": {"x": 1}, "execution_trace": [{"step": 1}]}
    last_result = repo_runtime_adapter_last_result(source)
    trace = repo_runtime_adapter_execution_trace(source)

    last_result["x"] = 2
    trace[0]["step"] = 2

    assert source["last_result"]["x"] == 1
    assert source["execution_trace"][0]["step"] == 1


def test_repo_runtime_adapter_execution_trace_from_nested_result() -> None:
    source = {"runner_result": {"execution_trace": [{"step": "nested"}]}}
    trace = repo_runtime_adapter_execution_trace(source)
    trace[0]["step"] = "changed"
    assert source["runner_result"]["execution_trace"][0]["step"] == "nested"
