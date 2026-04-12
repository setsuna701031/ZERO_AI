from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


WORKSPACE_ROOT = os.path.abspath("workspace")
SHARED_DIR = os.path.join(WORKSPACE_ROOT, "shared")
INPUT_PATH = os.path.join(SHARED_DIR, "input.txt")
OUTPUT_PATH = os.path.join(SHARED_DIR, "summary.txt")
TRACE_PATH = os.path.join(SHARED_DIR, "document_flow_trace.json")


def ensure_dirs() -> None:
    os.makedirs(SHARED_DIR, exist_ok=True)


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text_file(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_json_file(path: str, data: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_llm_client() -> Any:
    try:
        from core.system.llm_client import LocalLLMClient
    except Exception as e:
        raise RuntimeError(f"Failed to import LocalLLMClient: {e}") from e

    try:
        client = LocalLLMClient()
    except Exception as e:
        raise RuntimeError(f"Failed to initialize LocalLLMClient: {e}") from e

    return client


def call_llm(llm_client: Any, prompt: str) -> str:
    methods = [
        ("chat", True),
        ("ask", True),
        ("generate", True),
    ]

    for method_name, enabled in methods:
        if not enabled:
            continue
        method = getattr(llm_client, method_name, None)
        if callable(method):
            result = method(prompt)
            if isinstance(result, str):
                return result.strip()
            if isinstance(result, dict):
                for key in ("final_answer", "answer", "response", "message", "content", "text"):
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result).strip()

    raise RuntimeError("No usable chat/ask/generate method found on llm_client")


def build_summary_prompt(document_text: str) -> str:
    return f"""You are a document-processing agent.

Read the document below and produce a clean English summary.

Requirements:
1. Start with a short 2-4 sentence executive summary
2. Then provide 5-10 bullet points with the main takeaways
3. If the document contains action items, decisions, or risks, list them in separate sections
4. Do not invent details that are not in the source text
5. Write the entire output in English
6. Keep the result concise, readable, and demo-friendly

Document content:
--------------------
{document_text}
--------------------
"""


def build_trace(
    *,
    runtime_info: Optional[Dict[str, Any]],
    input_path: str,
    output_path: str,
    input_chars: int,
    summary_chars: int,
    status: str,
    error: str = "",
) -> Dict[str, Any]:
    return {
        "flow": "document_summary_demo",
        "status": status,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "workspace_root": WORKSPACE_ROOT,
        "shared_dir": SHARED_DIR,
        "input_path": input_path,
        "output_path": output_path,
        "trace_path": TRACE_PATH,
        "input_chars": input_chars,
        "summary_chars": summary_chars,
        "runtime_info": runtime_info or {},
        "error": error,
        "steps": [
            {
                "step": 1,
                "name": "read_input",
                "path": input_path,
            },
            {
                "step": 2,
                "name": "summarize_with_llm",
            },
            {
                "step": 3,
                "name": "write_summary",
                "path": output_path,
            },
        ],
    }


def main() -> int:
    ensure_dirs()

    if not os.path.exists(INPUT_PATH):
        example_text = (
            "ZERO is a local-first engineering agent prototype.\n"
            "This is an example input file for the document-processing demo.\n"
            "Replace this content with your own text and run the script again.\n"
        )
        write_text_file(INPUT_PATH, example_text)
        print(f"Input file not found. Created example file: {INPUT_PATH}")
        print("Please edit input.txt and run the script again.")
        return 1

    try:
        document_text = read_text_file(INPUT_PATH).strip()
    except Exception as e:
        print(f"Failed to read input.txt: {e}")
        return 1

    if not document_text:
        print(f"input.txt is empty: {INPUT_PATH}")
        return 1

    try:
        llm_client = load_llm_client()
    except Exception as e:
        print(str(e))
        return 1

    runtime_info: Dict[str, Any] = {}
    get_runtime_info = getattr(llm_client, "get_runtime_info", None)
    if callable(get_runtime_info):
        try:
            info = get_runtime_info()
            if isinstance(info, dict):
                runtime_info = info
        except Exception:
            runtime_info = {}

    prompt = build_summary_prompt(document_text)

    try:
        summary_text = call_llm(llm_client, prompt).strip()
    except Exception as e:
        trace = build_trace(
            runtime_info=runtime_info,
            input_path=INPUT_PATH,
            output_path=OUTPUT_PATH,
            input_chars=len(document_text),
            summary_chars=0,
            status="failed",
            error=str(e),
        )
        write_json_file(TRACE_PATH, trace)
        print(f"LLM summarization failed: {e}")
        print(f"trace: {TRACE_PATH}")
        return 1

    if not summary_text:
        trace = build_trace(
            runtime_info=runtime_info,
            input_path=INPUT_PATH,
            output_path=OUTPUT_PATH,
            input_chars=len(document_text),
            summary_chars=0,
            status="failed",
            error="LLM returned empty content",
        )
        write_json_file(TRACE_PATH, trace)
        print("LLM returned empty content")
        print(f"trace: {TRACE_PATH}")
        return 1

    output_text = (
        "# Document Summary\n\n"
        f"Source file: {INPUT_PATH}\n\n"
        "----\n\n"
        f"{summary_text.strip()}\n"
    )

    try:
        write_text_file(OUTPUT_PATH, output_text)
    except Exception as e:
        trace = build_trace(
            runtime_info=runtime_info,
            input_path=INPUT_PATH,
            output_path=OUTPUT_PATH,
            input_chars=len(document_text),
            summary_chars=len(summary_text),
            status="failed",
            error=f"Failed to write summary.txt: {e}",
        )
        write_json_file(TRACE_PATH, trace)
        print(f"Failed to write summary.txt: {e}")
        print(f"trace: {TRACE_PATH}")
        return 1

    trace = build_trace(
        runtime_info=runtime_info,
        input_path=INPUT_PATH,
        output_path=OUTPUT_PATH,
        input_chars=len(document_text),
        summary_chars=len(summary_text),
        status="finished",
        error="",
    )
    write_json_file(TRACE_PATH, trace)

    print("Document processing completed")
    print(f"input: {INPUT_PATH}")
    print(f"summary: {OUTPUT_PATH}")
    print(f"trace: {TRACE_PATH}")

    preview = summary_text[:300].strip()
    if preview:
        print("")
        print("summary preview:")
        print(preview)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())