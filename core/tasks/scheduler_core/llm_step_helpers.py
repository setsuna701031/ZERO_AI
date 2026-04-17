from __future__ import annotations

import copy
from typing import Any, Dict, Optional


_TEXT_KEYS = (
    "text",
    "content",
    "message",
    "response",
    "final_answer",
    "stdout",
    "checked_text",
)


def _extract_text_deep(payload: Any, depth: int = 0) -> str:
    if depth > 8:
        return ""

    if payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        for key in _TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value

        # 常見巢狀層
        for nested_key in ("result", "raw", "data", "payload", "previous_result"):
            nested = payload.get(nested_key)
            text = _extract_text_deep(nested, depth + 1)
            if text.strip():
                return text

    if isinstance(payload, list):
        for item in reversed(payload):
            text = _extract_text_deep(item, depth + 1)
            if text.strip():
                return text

    return ""


def _extract_previous_text_from_task(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return ""

    # 1. 先看 last_step_result
    last = task.get("last_step_result")
    text = _extract_text_deep(last)
    if text.strip():
        return text

    # 2. 再看 step_results，從最後一個往前找
    step_results = task.get("step_results", [])
    if isinstance(step_results, list) and step_results:
        for item in reversed(step_results):
            text = _extract_text_deep(item)
            if text.strip():
                return text

    # 3. 再看 results，從最後一個往前找
    results = task.get("results", [])
    if isinstance(results, list) and results:
        for item in reversed(results):
            text = _extract_text_deep(item)
            if text.strip():
                return text

    # 4. execution_log 也補抓一次
    execution_log = task.get("execution_log", [])
    if isinstance(execution_log, list) and execution_log:
        for item in reversed(execution_log):
            text = _extract_text_deep(item)
            if text.strip():
                return text

    return ""


def execute_llm_step(
    scheduler: Any,
    task: Dict[str, Any],
    step: Dict[str, Any],
    step_type: str,
) -> Optional[Dict[str, Any]]:
    if step_type not in {"llm", "llm_generate"}:
        return None

    previous_text = _extract_previous_text_from_task(task)
    prompt_template = str(step.get("prompt_template") or step.get("prompt") or "").strip()
    prompt = prompt_template.replace("{{file_content}}", previous_text)

    step_executor = getattr(scheduler, "step_executor", None)
    result_payload: Dict[str, Any]

    if step_executor is not None:
        try:
            if hasattr(step_executor, "execute_step") and callable(step_executor.execute_step):
                step_result = step_executor.execute_step(
                    task=task,
                    step=copy.deepcopy(step),
                    context={"file_content": previous_text},
                    step_index=int(task.get("current_step_index", 0) or 0),
                    step_count=len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 1,
                    previous_result=task.get("last_step_result"),
                )
            elif hasattr(step_executor, "execute") and callable(step_executor.execute):
                step_result = step_executor.execute(
                    step=copy.deepcopy(step),
                    context={"file_content": previous_text},
                )
            else:
                step_result = None
        except TypeError:
            try:
                step_result = step_executor.execute_step(
                    task=task,
                    step=copy.deepcopy(step),
                    context={"file_content": previous_text},
                )
            except Exception as e:
                raise RuntimeError(f"llm step execution failed: {e}")
        except Exception as e:
            raise RuntimeError(f"llm step execution failed: {e}")

        if isinstance(step_result, dict):
            result_payload = copy.deepcopy(step_result)
        else:
            result_payload = {"text": str(step_result or "")}

    elif getattr(scheduler, "llm_client", None) is not None:
        client = scheduler.llm_client
        if hasattr(client, "chat") and callable(client.chat):
            llm_out = client.chat(prompt)
        elif hasattr(client, "generate") and callable(client.generate):
            llm_out = client.generate(prompt)
        else:
            raise RuntimeError("llm_client has no chat/generate method")
        result_payload = {"text": str(llm_out or "")}

    else:
        raise RuntimeError("no llm backend available for llm step")

    final_text = _extract_text_deep(result_payload)
    if not final_text and isinstance(result_payload, dict):
        final_text = str(result_payload)

    return {
        "type": step_type,
        "mode": str(step.get("mode") or ""),
        "prompt": prompt,
        "prompt_template": prompt_template,
        "input_text": previous_text,
        "text": final_text,
        "content": final_text,
        "result": result_payload,
    }