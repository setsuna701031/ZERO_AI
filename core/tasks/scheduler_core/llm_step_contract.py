from __future__ import annotations

from typing import Any, Dict


LLM_STEP_CONTRACT_VERSION = "llm_step_contract.v1"
LLM_RUNTIME_CONTRACT_VERSION = "llm_runtime_contract.v1"

LLM_MODES = {
    "summary": "summary",
    "summarize": "summary",
    "document_summary": "summary",
    "action_items": "action_items",
    "action-items": "action_items",
    "actionitems": "action_items",
    "general": "general",
    "": "general",
}


def normalize_llm_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return LLM_MODES.get(raw, "general")


def llm_contract_metadata(step: Dict[str, Any], *, mode: str, input_binding: str) -> Dict[str, Any]:
    planner_contract_version = str(step.get("planner_contract_version") or "")
    return {
        "llm_contract_version": LLM_STEP_CONTRACT_VERSION,
        "planner_contract_version": planner_contract_version,
        "runtime_contract_version": LLM_RUNTIME_CONTRACT_VERSION,
        "input_binding": input_binding,
        "llm_mode": mode,
    }


def llm_contract_error(
    *,
    step: Dict[str, Any],
    mode: str,
    input_binding: str,
    error_type: str,
    message: str,
) -> Dict[str, Any]:
    payload = {
        "ok": False,
        "type": str(step.get("type") or "llm"),
        "action": "llm_contract_failed",
        "status": "failed",
        "mode": mode,
        "message": message,
        "final_answer": message,
        "error_type": error_type,
        "error": {
            "type": error_type,
            "message": message,
            "retryable": False,
        },
    }
    payload.update(llm_contract_metadata(step, mode=mode, input_binding=input_binding))
    return payload


def build_llm_contract_request(
    *,
    step: Dict[str, Any],
    prompt: str,
    prompt_template: str,
    input_text: str,
    mode: str,
    input_binding: str,
) -> Dict[str, Any]:
    request = {
        "llm_contract_version": LLM_STEP_CONTRACT_VERSION,
        "mode": mode,
        "llm_mode": mode,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "input_text": input_text,
        "input_binding": input_binding,
        "declared_input": input_binding,
        "planner_contract_version": str(step.get("planner_contract_version") or ""),
        "runtime_contract_version": LLM_RUNTIME_CONTRACT_VERSION,
    }
    return request


__all__ = [
    "LLM_RUNTIME_CONTRACT_VERSION",
    "LLM_STEP_CONTRACT_VERSION",
    "build_llm_contract_request",
    "llm_contract_error",
    "llm_contract_metadata",
    "normalize_llm_mode",
]
