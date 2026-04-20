from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def plan_structured_document_task(
    *,
    context: Optional[Dict[str, Any]] = None,
    route: Any = None,
    kwargs: Optional[Dict[str, Any]] = None,
    trace_logger: Any = None,
) -> Optional[List[Dict[str, Any]]]:
    context = context or {}
    kwargs = kwargs or {}

    payload = extract_structured_document_payload(
        context=context,
        route=route,
        kwargs=kwargs,
    )
    if not payload:
        return None

    task_type = str(payload.get("task_type") or "").strip().lower()
    mode = str(payload.get("mode") or "").strip().lower()
    input_file = str(payload.get("input_file") or "").strip()
    output_file = str(payload.get("output_file") or "").strip()

    if task_type != "document":
        return None

    if mode in ("summary", "summarize", "summarise"):
        source_path = input_file or "input.txt"
        output_path = output_file or "summary.txt"

        _log(
            trace_logger,
            title="structured document task detected",
            message=f"mode=summary, source={source_path}, output={output_path}",
            raw={"payload": payload},
        )
        return build_summary_steps(source_path, output_path)

    if mode in ("action_items", "action-items", "actionitems", "todo", "to_do"):
        source_path = input_file or "input.txt"
        output_path = output_file or "action_items.txt"

        _log(
            trace_logger,
            title="structured document task detected",
            message=f"mode=action_items, source={source_path}, output={output_path}",
            raw={"payload": payload},
        )
        return build_action_items_steps(source_path, output_path)

    if mode in ("requirement_pack", "requirement-pack", "requirementpack"):
        source_path = input_file or "requirement.txt"

        _log(
            trace_logger,
            title="structured document task detected",
            message=f"mode=requirement_pack, source={source_path}",
            raw={"payload": payload},
        )
        return build_requirement_pack_steps(source_path)

    _log(
        trace_logger,
        title="structured document task ignored",
        message=f"unsupported mode={mode or '(empty)'}",
        raw={"payload": payload},
    )
    return None


def extract_structured_document_payload(
    *,
    context: Dict[str, Any],
    route: Any = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    kwargs = kwargs or {}

    candidate_dicts: List[Dict[str, Any]] = []

    if isinstance(context, dict):
        candidate_dicts.append(context)

        for key in ("task", "task_payload", "task_data", "payload", "document_task"):
            value = context.get(key)
            if isinstance(value, dict):
                candidate_dicts.append(value)

    if isinstance(route, dict):
        candidate_dicts.append(route)
        for key in ("task", "payload", "document_task"):
            value = route.get(key)
            if isinstance(value, dict):
                candidate_dicts.append(value)

    if isinstance(kwargs, dict):
        candidate_dicts.append(kwargs)
        for key in ("task", "task_payload", "payload", "document_task"):
            value = kwargs.get(key)
            if isinstance(value, dict):
                candidate_dicts.append(value)

    for candidate in candidate_dicts:
        normalized = normalize_structured_document_payload(candidate)
        if normalized is not None:
            return normalized

    return None


def normalize_structured_document_payload(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None

    task_type = pick_first_non_empty(
        data,
        [
            "task_type",
            "type",
            "job_type",
            "workflow_type",
        ],
    )
    mode = pick_first_non_empty(
        data,
        [
            "mode",
            "document_mode",
            "task_mode",
            "operation",
            "action",
        ],
    )
    input_file = pick_first_non_empty(
        data,
        [
            "input_file",
            "input_path",
            "source_file",
            "source_path",
            "file_path",
            "path",
        ],
    )
    output_file = pick_first_non_empty(
        data,
        [
            "output_file",
            "output_path",
            "target_file",
            "target_path",
            "result_file",
            "result_path",
        ],
    )

    if not task_type:
        return None

    lowered_type = str(task_type).strip().lower()
    if lowered_type not in ("document", "doc", "document_flow"):
        return None

    normalized: Dict[str, Any] = {
        "task_type": "document",
        "mode": str(mode or "").strip(),
        "input_file": str(input_file or "").strip(),
        "output_file": str(output_file or "").strip(),
    }

    if not normalized["mode"]:
        inferred_mode = infer_document_mode_from_output(normalized["output_file"])
        if inferred_mode:
            normalized["mode"] = inferred_mode

    if not normalized["mode"]:
        return None

    return normalized


def pick_first_non_empty(data: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def infer_document_mode_from_output(output_file: str) -> str:
    lowered = str(output_file or "").strip().lower()
    if not lowered:
        return ""

    if "action_items" in lowered or "action-items" in lowered or "actionitems" in lowered:
        return "action_items"
    if "summary" in lowered:
        return "summary"
    if (
        "acceptance_checklist" in lowered
        or "implementation_plan" in lowered
        or "project_summary" in lowered
    ):
        return "requirement_pack"

    return ""


def plan_document_flow(
    *,
    text: str,
    trace_logger: Any = None,
) -> Optional[List[Dict[str, Any]]]:
    lowered = normalize_document_flow_text(text)
    all_paths = extract_all_file_paths(text)

    explicit_source = extract_document_source_path(text, all_paths)
    explicit_output = extract_document_output_path(text, all_paths)

    explicit_action_patterns = [
        r"read\s+.+?\s+and\s+extract\s+action\s+items\s+into\s+.+",
        r"extract\s+action\s+items\s+from\s+.+?\s+into\s+.+",
        r"extract\s+action\s+items\s+into\s+.+?\s+from\s+.+",
        r".+?\s*->\s*.+",
    ]
    explicit_summary_patterns = [
        r"read\s+.+?\s+and\s+summari[sz]e\s+(?:it\s+)?into\s+.+",
        r"summari[sz]e\s+.+?\s+into\s+.+",
        r"summary\s+.+?\s+into\s+.+",
        r".+?\s*->\s*.+",
    ]

    action_keywords = [
        "action item",
        "action items",
        "extract action items",
        "todo",
        "to-do",
        "行動項目",
        "待辦事項",
    ]
    summary_keywords = [
        "summary",
        "summarize",
        "summarise",
        "摘要",
        "總結",
    ]

    wants_action_items = any(k in lowered for k in action_keywords)
    wants_summary = any(k in lowered for k in summary_keywords)

    if wants_action_items:
        source_path = explicit_source or choose_default_document_source(all_paths) or "input.txt"
        output_path = explicit_output or choose_default_action_items_output(all_paths) or "action_items.txt"

        if looks_like_document_flow_request(text):
            steps = build_action_items_steps(source_path, output_path)
            _log(
                trace_logger,
                title="document flow detected",
                message=text,
                raw={"steps": steps},
            )
            return steps

        for pattern in explicit_action_patterns:
            if re.search(pattern, lowered):
                steps = build_action_items_steps(source_path, output_path)
                _log(
                    trace_logger,
                    title="document flow detected",
                    message=text,
                    raw={"steps": steps},
                )
                return steps

    requirement_pack = extract_requirement_pack_request(text, all_paths)
    if requirement_pack is not None:
        source_path = requirement_pack.get("input_file") or "requirement.txt"
        steps = build_requirement_pack_steps(source_path)
        _log(
            trace_logger,
            title="document flow detected",
            message=text,
            raw={"steps": steps},
        )
        return steps

    if wants_summary:
        source_path = explicit_source or choose_default_document_source(all_paths) or "input.txt"
        output_path = explicit_output or choose_default_summary_output(all_paths) or "summary.txt"

        if looks_like_document_flow_request(text):
            steps = build_summary_steps(source_path, output_path)
            _log(
                trace_logger,
                title="document flow detected",
                message=text,
                raw={"steps": steps},
            )
            return steps

        for pattern in explicit_summary_patterns:
            if re.search(pattern, lowered):
                steps = build_summary_steps(source_path, output_path)
                _log(
                    trace_logger,
                    title="document flow detected",
                    message=text,
                    raw={"steps": steps},
                )
                return steps

    has_input_txt = "input.txt" in lowered
    has_action_items_txt = "action_items.txt" in lowered
    has_summary_txt = "summary.txt" in lowered

    if has_input_txt and (wants_action_items or has_action_items_txt):
        steps = build_action_items_steps("input.txt", explicit_output or "action_items.txt")
        _log(
            trace_logger,
            title="document flow detected",
            message=text,
            raw={"steps": steps},
        )
        return steps

    if has_input_txt and (wants_summary or has_summary_txt):
        steps = build_summary_steps("input.txt", explicit_output or "summary.txt")
        _log(
            trace_logger,
            title="document flow detected",
            message=text,
            raw={"steps": steps},
        )
        return steps

    return None


def normalize_document_flow_text(text: str) -> str:
    lowered = str(text or "").strip().lower()

    prefixes = [
        "task ",
        "create task ",
        "new task ",
        "submit task ",
        "please ",
        "pls ",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if lowered.startswith(prefix):
                lowered = lowered[len(prefix):].strip()
                changed = True

    return lowered


def extract_requirement_pack_request(text: str, all_paths: List[str]) -> Optional[Dict[str, str]]:
    stripped = str(text or "").strip()
    lowered = normalize_document_flow_text(text)

    requirement_markers = [
        "requirement",
        "requirements",
        "spec",
        "specification",
        "需求",
        "需求書",
    ]
    output_markers = [
        "project_summary.txt",
        "implementation_plan.txt",
        "acceptance_checklist.txt",
    ]

    has_requirement_source = any(marker in lowered for marker in requirement_markers)
    has_requirement_outputs = all(marker in lowered for marker in output_markers)

    if not has_requirement_outputs:
        return None

    source_path = extract_document_source_path(stripped, all_paths)
    if not source_path:
        if has_requirement_source:
            source_path = "requirement.txt"
        else:
            return None

    return {
        "task_type": "document",
        "mode": "requirement_pack",
        "input_file": source_path,
    }


def looks_like_document_flow_request(text: str) -> bool:
    lowered = normalize_document_flow_text(text)
    doc_markers = [
        "read ",
        "summarize ",
        "summarise ",
        "summary ",
        "extract action items",
        "action items",
        "摘要",
        "總結",
        "行動項目",
        "待辦事項",
        "into ",
        "from ",
        "->",
    ]
    return any(marker in lowered for marker in doc_markers)


def extract_document_source_path(text: str, all_paths: List[str]) -> Optional[str]:
    stripped = str(text or "").strip()

    patterns = [
        r"\bfrom\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bread\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bsummari[sz]e\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bsummary\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bextract\s+action\s+items\s+from\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, stripped, flags=re.IGNORECASE)
        if m:
            value = str(m.group(1)).strip()
            if value:
                return value

    arrow = extract_arrow_paths(stripped)
    if arrow is not None:
        source_path, _ = arrow
        return source_path

    if all_paths:
        return all_paths[0]

    return None


def extract_document_output_path(text: str, all_paths: List[str]) -> Optional[str]:
    stripped = str(text or "").strip()

    patterns = [
        r"\binto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bwrite\s+.+?\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\boutput\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, stripped, flags=re.IGNORECASE)
        if m:
            value = str(m.group(1)).strip()
            if value:
                return value

    arrow = extract_arrow_paths(stripped)
    if arrow is not None:
        _, output_path = arrow
        return output_path

    if len(all_paths) >= 2:
        return all_paths[-1]

    return None


def extract_arrow_paths(text: str) -> Optional[Tuple[str, str]]:
    stripped = str(text or "").strip()
    m = re.search(
        r"([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\s*->\s*([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))",
        stripped,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    source_path = str(m.group(1)).strip()
    output_path = str(m.group(2)).strip()
    if not source_path or not output_path:
        return None

    return source_path, output_path


def extract_all_file_paths(text: str) -> List[str]:
    if not text:
        return []

    results: List[str] = []
    pattern = r"\b([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b"
    for m in re.finditer(pattern, text):
        value = str(m.group(1)).strip()
        if value and value not in results:
            results.append(value)
    return results


def choose_default_document_source(all_paths: List[str]) -> Optional[str]:
    for path in all_paths:
        lowered = path.lower()
        if lowered.endswith((".txt", ".md", ".log", ".json", ".csv", ".yaml", ".yml")):
            return path
    return None


def choose_default_summary_output(all_paths: List[str]) -> Optional[str]:
    for path in all_paths:
        lowered = path.lower()
        if "summary" in lowered:
            return path
    return None


def choose_default_action_items_output(all_paths: List[str]) -> Optional[str]:
    for path in all_paths:
        lowered = path.lower()
        if "action_items" in lowered or "action-items" in lowered or "actionitems" in lowered:
            return path
    return None


def build_action_items_steps(source_path: str, output_path: str) -> List[Dict[str, Any]]:
    prompt_template = (
        "You are an assistant that extracts action items from notes.\n\n"
        "Read the document content below and produce a clean plain-text file.\n\n"
        "Output rules:\n"
        "1. Output title must be exactly: ACTION ITEMS\n"
        "2. For each item use exactly this format:\n"
        "   1. Owner: <name or Unassigned>\n"
        "      Task: <clear action>\n"
        "      Due: <deadline or Not specified>\n"
        "3. If no explicit owner, use Unassigned.\n"
        "4. If no explicit deadline or time commitment for the action, use Not specified.\n"
        "5. Do not output JSON.\n"
        "6. Do not add explanations before or after the list.\n"
        "7. Only include real action items. Do not include pure status statements or background facts.\n\n"
        "Due extraction rules:\n"
        "- Preserve explicit due phrases when they belong to the action, such as:\n"
        "  by Monday, by Friday, today, tomorrow, this afternoon, this evening, next week, next month.\n"
        "- If a sentence says someone will do something by a certain day, keep that due phrase.\n"
        "- If a sentence describes a past event, such as last night, yesterday, previously, do not treat that as a due date unless it clearly applies to the action.\n"
        "- Prefer the deadline phrase exactly as written in the notes when reasonable.\n"
        "- If the time phrase belongs to the action, keep it in Due.\n"
        "- If there is no due phrase for the action, write Not specified.\n\n"
        "Owner extraction rules:\n"
        "- Use a person's name when explicitly stated.\n"
        "- For group statements like 'we should', use Unassigned unless a real owner is named.\n\n"
        "Task extraction rules:\n"
        "- Rewrite each task as a short, clear action.\n"
        "- Do not copy unnecessary background context into Task unless it is needed for clarity.\n\n"
        "Document content:\n"
        "{{file_content}}\n"
    )

    return [
        {
            "type": "read_file",
            "path": source_path,
        },
        {
            "type": "llm",
            "mode": "action_items",
            "prompt_template": prompt_template,
        },
        {
            "type": "write_file",
            "path": output_path,
            "scope": "shared",
            "use_previous_text": True,
        },
    ]


def build_summary_steps(source_path: str, output_path: str) -> List[Dict[str, Any]]:
    prompt_template = (
        "Summarize the following document into a concise plain-text summary.\n\n"
        "Rules:\n"
        "1. Keep it clear and short.\n"
        "2. Do not use JSON.\n"
        "3. Do not add extra commentary.\n\n"
        "Document content:\n"
        "{{file_content}}\n"
    )

    return [
        {
            "type": "read_file",
            "path": source_path,
        },
        {
            "type": "llm",
            "mode": "summary",
            "prompt_template": prompt_template,
        },
        {
            "type": "write_file",
            "path": output_path,
            "scope": "shared",
            "use_previous_text": True,
        },
    ]


def build_requirement_pack_steps(source_path: str) -> List[Dict[str, Any]]:
    summary_prompt = (
        "Read the requirement document below and produce a concise plain-text project summary.\n\n"
        "Required sections:\n"
        "1. Project Goal\n"
        "2. Key Requirements\n"
        "3. Constraints\n"
        "4. Expected Deliverables\n\n"
        "Rules:\n"
        "- Keep it clear and engineering-oriented.\n"
        "- Do not use JSON.\n"
        "- Do not add extra commentary outside the summary.\n\n"
        "Requirement document:\n"
        "{{file_content}}\n"
    )

    implementation_prompt = (
        "Read the requirement document below and produce a plain-text implementation plan.\n\n"
        "Required sections:\n"
        "1. Implementation Steps\n"
        "2. Recommended Execution Order\n"
        "3. Risks and Dependencies\n"
        "4. Verification Focus\n\n"
        "Rules:\n"
        "- Keep the plan practical and engineering-oriented.\n"
        "- Use numbered steps where useful.\n"
        "- Do not use JSON.\n"
        "- Do not add extra commentary outside the plan.\n\n"
        "Requirement document:\n"
        "{{file_content}}\n"
    )

    checklist_prompt = (
        "Read the requirement document below and produce a plain-text acceptance checklist.\n\n"
        "The output must contain exactly these section titles:\n"
        "Acceptance Criteria\n"
        "Verification\n"
        "Deliverable\n\n"
        "Rules:\n"
        "- Each section must contain concrete bullet points.\n"
        "- Keep it plain text.\n"
        "- Do not use JSON.\n"
        "- Do not add extra commentary outside the checklist.\n\n"
        "Requirement document:\n"
        "{{file_content}}\n"
    )

    return [
        {
            "type": "read_file",
            "path": source_path,
        },
        {
            "type": "llm",
            "mode": "summary",
            "prompt_template": summary_prompt,
        },
        {
            "type": "write_file",
            "path": "project_summary.txt",
            "scope": "shared",
            "use_previous_text": True,
        },
        {
            "type": "llm",
            "mode": "summary",
            "prompt_template": implementation_prompt,
        },
        {
            "type": "write_file",
            "path": "implementation_plan.txt",
            "scope": "shared",
            "use_previous_text": True,
        },
        {
            "type": "llm",
            "mode": "summary",
            "prompt_template": checklist_prompt,
        },
        {
            "type": "write_file",
            "path": "acceptance_checklist.txt",
            "scope": "shared",
            "use_previous_text": True,
        },
        {
            "type": "verify",
            "path": "acceptance_checklist.txt",
            "scope": "shared",
            "contains": "Acceptance Criteria",
        },
        {
            "type": "verify",
            "path": "acceptance_checklist.txt",
            "scope": "shared",
            "contains": "Verification",
        },
        {
            "type": "verify",
            "path": "acceptance_checklist.txt",
            "scope": "shared",
            "contains": "Deliverable",
        },
    ]


def _log(trace_logger: Any, title: str, message: str, raw: Optional[Dict[str, Any]] = None) -> None:
    if trace_logger is None:
        return
    try:
        trace_logger.log_decision(
            title=title,
            message=message,
            source="planner",
            raw=raw,
        )
    except Exception:
        return