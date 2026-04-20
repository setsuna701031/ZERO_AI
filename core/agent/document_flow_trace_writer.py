from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List


def maybe_write_document_flow_trace(
    *,
    steps: List[Dict[str, Any]],
    execution_result: Dict[str, Any],
    llm_client: Any = None,
    step_executor: Any = None,
    debug: bool = False,
) -> None:
    if not isinstance(execution_result, dict):
        return
    if not execution_result.get("ok", False):
        return
    if not isinstance(steps, list) or len(steps) < 3:
        return

    flow_kind = detect_document_flow_kind(steps)
    if not flow_kind:
        return

    step_results = execution_result.get("results")
    if not isinstance(step_results, list) or len(step_results) < 3:
        return

    read_result = get_result_payload(step_results, 0)
    llm_result = get_result_payload(step_results, 1)
    write_result = get_result_payload(step_results, 2)

    input_full_path = extract_path_from_payload(read_result) or default_shared_path("input.txt")
    output_full_path = extract_path_from_payload(write_result) or default_shared_path(
        "action_items.txt" if flow_kind == "action_items" else "summary.txt"
    )

    input_content = extract_content_from_payload(read_result)
    output_content = extract_content_from_payload(write_result)
    if not output_content:
        output_content = extract_content_from_payload(llm_result)

    runtime_info = get_runtime_info(
        llm_client=llm_client,
        step_executor=step_executor,
    )

    trace = build_document_flow_trace(
        flow_kind=flow_kind,
        input_path=input_full_path,
        output_path=output_full_path,
        input_text=input_content,
        output_text=output_content,
        runtime_info=runtime_info,
    )

    trace_path = default_shared_path("document_flow_trace.json")
    os.makedirs(os.path.dirname(trace_path), exist_ok=True)
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)

    if debug:
        print(f"[DocumentFlowTraceWriter] wrote document flow trace: {trace_path}")


def detect_document_flow_kind(steps: List[Dict[str, Any]]) -> str:
    if len(steps) < 3:
        return ""

    step1 = steps[0] if isinstance(steps[0], dict) else {}
    step2 = steps[1] if isinstance(steps[1], dict) else {}
    step3 = steps[2] if isinstance(steps[2], dict) else {}

    type1 = str(step1.get("type", "")).strip().lower()
    type2 = str(step2.get("type", "")).strip().lower()
    type3 = str(step3.get("type", "")).strip().lower()

    mode2 = str(step2.get("mode", "")).strip().lower()
    path3 = str(step3.get("path", "")).strip().lower()

    if type1 != "read_file" or type2 not in {"llm", "llm_generate"} or type3 != "write_file":
        return ""

    if mode2 == "action_items" or "action_items" in path3 or "action-items" in path3:
        return "action_items"

    if mode2 == "summary" or "summary" in path3:
        return "summary"

    return ""


def build_document_flow_trace(
    *,
    flow_kind: str,
    input_path: str,
    output_path: str,
    input_text: str,
    output_text: str,
    runtime_info: Dict[str, Any],
) -> Dict[str, Any]:
    if flow_kind == "action_items":
        return {
            "flow": "document_action_items_demo",
            "status": "finished",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "workspace_root": os.path.abspath("workspace"),
            "shared_dir": default_shared_dir(),
            "input_path": input_path,
            "output_path": output_path,
            "trace_path": default_shared_path("document_flow_trace.json"),
            "input_chars": len(input_text),
            "action_items_chars": len(output_text),
            "runtime_info": runtime_info,
            "error": "",
            "steps": [
                {"step": 1, "name": "read_input", "path": input_path},
                {"step": 2, "name": "extract_action_items"},
                {"step": 3, "name": "write_action_items", "path": output_path},
            ],
        }

    return {
        "flow": "document_summary_demo",
        "status": "finished",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "workspace_root": os.path.abspath("workspace"),
        "shared_dir": default_shared_dir(),
        "input_path": input_path,
        "output_path": output_path,
        "trace_path": default_shared_path("document_flow_trace.json"),
        "input_chars": len(input_text),
        "summary_chars": len(output_text),
        "runtime_info": runtime_info,
        "error": "",
        "steps": [
            {"step": 1, "name": "read_input", "path": input_path},
            {"step": 2, "name": "summarize_document"},
            {"step": 3, "name": "write_summary", "path": output_path},
        ],
    }


def get_result_payload(execution_results: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
    if not isinstance(execution_results, list):
        return {}
    if index < 0 or index >= len(execution_results):
        return {}
    item = execution_results[index]
    if not isinstance(item, dict):
        return {}
    result = item.get("result")
    if isinstance(result, dict):
        return result
    return {}


def extract_path_from_payload(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    result_block = payload.get("result")
    if isinstance(result_block, dict):
        for key in ("full_path", "path"):
            value = result_block.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("full_path", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_content_from_payload(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    result_block = payload.get("result")
    if isinstance(result_block, dict):
        for key in ("content", "text", "message"):
            value = result_block.get(key)
            if isinstance(value, str):
                return value
    for key in ("content", "text", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def get_runtime_info(
    *,
    llm_client: Any = None,
    step_executor: Any = None,
) -> Dict[str, Any]:
    effective_llm_client = llm_client
    if effective_llm_client is None and step_executor is not None:
        effective_llm_client = getattr(step_executor, "llm_client", None)

    if effective_llm_client is None:
        return {}

    get_runtime_info_fn = getattr(effective_llm_client, "get_runtime_info", None)
    if callable(get_runtime_info_fn):
        try:
            info = get_runtime_info_fn()
            if isinstance(info, dict):
                return info
        except Exception:
            return {}

    return {
        "plugin_name": str(getattr(effective_llm_client, "plugin_name", "") or ""),
        "provider": str(getattr(effective_llm_client, "provider", "") or ""),
        "base_url": str(getattr(effective_llm_client, "base_url", "") or ""),
        "model": str(getattr(effective_llm_client, "model", "") or ""),
        "coder_model": str(getattr(effective_llm_client, "coder_model", "") or ""),
        "timeout": getattr(effective_llm_client, "timeout", None),
    }


def default_shared_dir() -> str:
    return os.path.abspath(os.path.join("workspace", "shared"))


def default_shared_path(filename: str) -> str:
    return os.path.abspath(os.path.join("workspace", "shared", filename))