from __future__ import annotations

from core.agent.agent_component_invoker import call_router
from core.system.router import Router


def test_router_accepts_legacy_positional_contract() -> None:
    router = Router()

    assert router.route("你好")["mode"] == "llm"
    assert router.route("建立任務 測試")["mode"] == "task"


def test_router_accepts_agent_component_keyword_contract() -> None:
    router = Router()

    result = router.route(
        context={"mode": "chat"},
        user_input="讀取 workspace/shared/input.txt",
        source="agent_loop",
    )

    assert result["mode"] == "direct"
    assert result["step"] == {
        "type": "read_file",
        "path": "workspace/shared/input.txt",
    }


def test_call_router_no_longer_reports_source_contract_mismatch() -> None:
    router = Router()

    result = call_router(
        router,
        context={"mode": "chat"},
        user_input="Task name:",
    )

    assert isinstance(result, dict)
    assert result.get("component_contract_mismatch") is not True
    assert result.get("ok") is not False
    assert result.get("mode") in {"llm", "task", "direct"}


def run_router_test():
    print("=== Router Test Start ===")

    router = Router()

    test_inputs = [
        "你好",
        "幫我分析這個專案架構",
        "寫一個python函式",
        "執行 command dir",
        "讀取 workspace 裡的 task_memory.json",
    ]

    for user_input in test_inputs:
        print("\n=== Input ===")
        print(user_input)

        try:
            result = router.route(user_input)
        except Exception as exc:
            result = {"error": str(exc)}

        print("--- Route Result ---")
        print(result)

    print("\n=== Router Test End ===")


if __name__ == "__main__":
    run_router_test()
