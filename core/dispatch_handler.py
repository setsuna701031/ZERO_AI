from typing import Any, Callable, Dict, Optional


class DispatchHandler:
    """
    專門負責 tool / command 這類透過 tool_registry.execute(...)
    執行的共通流程。

    目標：
    1. 檢查 name 是否存在
    2. 檢查 tool_registry 是否可用
    3. 執行 registry.execute(...)
    4. 用外部 formatter 組 success / failure 回傳
    """

    @staticmethod
    def dispatch(
        registry: Any,
        name: Optional[str],
        payload: Any,
        missing_name_summary: str,
        missing_name_error: str,
        missing_registry_summary: str,
        missing_registry_error: str,
        execution_failure_summary: str,
        execution_failure_prefix: str,
        success_builder: Callable[[str, Any, Any], Dict[str, Any]],
        failure_builder: Callable[[str, Any, str], Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not name:
            return failure_builder(
                missing_name_summary,
                payload,
                missing_name_error,
            )

        if registry is None:
            return failure_builder(
                missing_registry_summary,
                payload,
                missing_registry_error,
            )

        try:
            result = registry.execute(name, payload)
            return success_builder(name, payload, result)
        except Exception as e:
            return failure_builder(
                name,
                payload,
                f"{execution_failure_prefix}:{str(e)}",
                override_summary=execution_failure_summary,
            )