from __future__ import annotations

import re
from typing import Any, Dict, Optional


SUMMARY_MODES = {"summary", "summarize", "document_summary"}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in (
            "content",
            "text",
            "message",
            "final_answer",
            "output_text",
            "stdout",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        nested = value.get("result")
        if isinstance(nested, dict):
            return _as_text(nested)
    return str(value)


def _extract_previous_text(previous_result: Any) -> str:
    if isinstance(previous_result, dict):
        direct = _as_text(previous_result)
        if direct.strip():
            return direct.strip()

        result = previous_result.get("result")
        if isinstance(result, dict):
            direct = _as_text(result)
            if direct.strip():
                return direct.strip()

        adapter = previous_result.get("adapter_payload")
        if isinstance(adapter, dict):
            direct = _as_text(adapter)
            if direct.strip():
                return direct.strip()

    return _as_text(previous_result).strip()


def deterministic_plain_text_summary(text: str, *, max_lines: int = 5, max_chars: int = 1200) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]

    if not paragraphs:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]

    if not paragraphs:
        return source[:max_chars].rstrip()

    summary = "\n".join(paragraphs[:max_lines]).strip()

    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip() + "..."

    return summary


def should_use_deterministic_summary(step: Any, previous_result: Any) -> bool:
    if not isinstance(step, dict):
        return False

    step_type = str(step.get("type") or step.get("action") or "").strip().lower()
    mode = str(step.get("mode") or "").strip().lower()

    if step_type not in {"llm", "llm_generate"}:
        return False

    if mode not in SUMMARY_MODES:
        return False

    previous_text = _extract_previous_text(previous_result)
    return bool(previous_text.strip())


def build_deterministic_summary_result(
    *,
    step: Dict[str, Any],
    previous_result: Any,
) -> Dict[str, Any]:
    mode = str(step.get("mode") or "summary").strip().lower() or "summary"
    prompt_template = str(step.get("prompt") or "")
    previous_text = _extract_previous_text(previous_result)
    summary = deterministic_plain_text_summary(previous_text)
    prompt = prompt_template.replace("{{file_content}}", previous_text)

    return {
        "ok": True,
        "type": "llm",
        "mode": mode,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "input_text": previous_text,
        "text": summary,
        "content": summary,
        "message": summary,
        "final_answer": summary,
        "result": {
            "prompt": prompt,
            "text": summary,
            "message": summary,
            "final_answer": summary,
            "deterministic_summary_fast_path": True,
            "llm_skipped": True,
        },
        "error": None,
    }


def install_deterministic_summary_handler(step_executor: Any) -> bool:
    if step_executor is None:
        return False

    execute_step = getattr(step_executor, "execute_step", None)
    if not callable(execute_step):
        return False

    if bool(getattr(step_executor, "_deterministic_summary_handler_installed", False)):
        return True

    original_execute_step = execute_step

    def execute_step_with_deterministic_summary(
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
        step_index: Optional[int] = None,
        step_count: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if should_use_deterministic_summary(step, previous_result):
            raw_result = build_deterministic_summary_result(
                step=step,
                previous_result=previous_result,
            )

            normalizer = getattr(step_executor, "_normalize_step_result", None)
            tracer = getattr(step_executor, "_attach_execution_trace", None)
            emit_after = getattr(step_executor, "_emit_evidence_after_result", None)

            if callable(normalizer):
                normalized = normalizer(
                    raw_result=raw_result,
                    step=dict(step or {}),
                    original_step=dict(step or {}),
                    task=task if isinstance(task, dict) else {},
                )
            else:
                normalized = dict(raw_result)

            normalized["deterministic_summary_fast_path"] = True

            if callable(tracer):
                normalized = tracer(dict(step or {}), normalized)

            if callable(emit_after):
                try:
                    emit_after(
                        step=dict(step or {}),
                        task=task if isinstance(task, dict) else {},
                        step_type="llm",
                        result=normalized,
                    )
                except Exception:
                    pass

            return normalized

        return original_execute_step(
            step=step,
            task=task,
            context=context,
            previous_result=previous_result,
            step_index=step_index,
            step_count=step_count,
            **kwargs,
        )

    step_executor.execute_step = execute_step_with_deterministic_summary
    step_executor._deterministic_summary_handler_installed = True
    return True


__all__ = [
    "SUMMARY_MODES",
    "deterministic_plain_text_summary",
    "should_use_deterministic_summary",
    "build_deterministic_summary_result",
    "install_deterministic_summary_handler",
]
