from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_memory_model import RuntimeActivityMemory, validate_runtime_activity_experience
from core.runtime.runtime_operator_session import fingerprint


QUERY_CONTRACT = "zero.runtime.agent_experience_query.v1"
CONTEXT_CONTRACT = "zero.runtime.agent_memory_context.v1"


def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _tokens(value: Any) -> set[str]: return set(re.findall(r"[a-z0-9_.\-/]{2,}|[\u4e00-\u9fff]{2,}", str(value or "").casefold()))
def _time(value: Any) -> float:
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError): return 0.0


def _experience_records(memory: Any) -> list[dict[str, Any]]:
    if isinstance(memory, RuntimeActivityMemory): return memory.experience_records()
    if isinstance(memory, Mapping):
        records = memory.get("records") or memory.get("experiences") or []
        if isinstance(records, Mapping): records = list(records.values())
        result = [_mapping(record) for record in records if isinstance(record, Mapping)]
        for record in result:
            reasons = validate_runtime_activity_experience(record)
            if reasons: raise ValueError(";".join(reasons))
        return result
    raise ValueError("runtime_activity_memory_required")


def query_relevant_experiences(memory: Any, query_text: str, *, operation_types: list[str] | None = None,
                               target_paths: list[str] | None = None, tags: list[str] | None = None,
                               workspace_context: str | None = None, risk_class: str | None = None,
                               top_k: int = 3) -> dict[str, Any]:
    text = str(query_text or "").strip()
    if not text: raise ValueError("memory_query_text_required")
    query_tokens = _tokens(" ".join([text] + list(operation_types or []) + list(target_paths or []) + list(tags or [])))
    matches = []
    for record in _experience_records(memory):
        record_tokens = _tokens(" ".join([str(record.get("normalized_task") or ""), " ".join(record.get("operation_types") or []), " ".join(record.get("target_paths") or []), " ".join(record.get("matched_keywords") or [])]))
        overlap = sorted(query_tokens & record_tokens)
        union = query_tokens | record_tokens
        similarity = len(overlap) / len(union) if union else 0.0
        query_names = {part.rsplit("/", 1)[-1] for part in target_paths or []}
        record_names = {str(part).replace("\\", "/").rsplit("/", 1)[-1] for part in record.get("target_paths") or []}
        if query_names & record_names: similarity += 0.25
        if set(operation_types or []) & set(record.get("operation_types") or []): similarity += 0.20
        if workspace_context and str(record.get("workspace_scope") or "").casefold() == str(workspace_context).casefold(): similarity += 0.05
        score = round(min(1.0, similarity), 6)
        if score <= 0: continue
        matches.append({"experience_id": record["experience_id"], "similarity_score": score, "matched_tokens": overlap, "outcome": record["outcome"], "summary": record.get("summary"), "lessons": deepcopy(record.get("lessons") or []), "reusable_patterns": deepcopy(record.get("reusable_patterns") or []), "avoid_patterns": deepcopy(record.get("avoid_patterns") or []), "source_references": deepcopy(record.get("source_references") or []), "created_at": record.get("created_at")})
    outcome_rank = {"completed": 2, "blocked": 1, "denied": 1, "failed": 1, "cancelled": 0}
    matches.sort(key=lambda item: (-item["similarity_score"], -outcome_rank.get(item["outcome"], 0), -_time(item.get("created_at")), item["experience_id"]))
    selected = matches[:min(3 if top_k is None else max(0, int(top_k)), 20)]
    value = {"contract": QUERY_CONTRACT, "query_text": text, "query_tokens": sorted(query_tokens), "operation_types": sorted(set(operation_types or [])), "target_paths": sorted(set(target_paths or [])), "tags": sorted(set(tags or [])), "workspace_context": workspace_context, "risk_class": risk_class, "matches": selected, "match_count": len(selected)}
    value["query_fingerprint"] = fingerprint(value); return value


def build_memory_context(memory: Any, query_text: str, *, operation_types: list[str] | None = None,
                         target_paths: list[str] | None = None, workspace_context: str | None = None,
                         risk_class: str | None = None, top_k: int = 3) -> dict[str, Any]:
    query = query_relevant_experiences(memory, query_text, operation_types=operation_types, target_paths=target_paths, workspace_context=workspace_context, risk_class=risk_class, top_k=min(3, max(0, int(top_k))))
    matches = query["matches"]
    successful = sorted(set(pattern for match in matches if match["outcome"] == "completed" for pattern in match["reusable_patterns"]))[:12]
    failures = sorted(set(pattern for match in matches if match["outcome"] != "completed" for pattern in match["avoid_patterns"]))[:12]
    validations = []
    if any(pattern in {"create_then_verify", "workspace_contained_write"} for pattern in successful): validations.extend(["verify_target_exists", "verify_content_hash"])
    if "path_traversal" in failures: validations.append("validate_workspace_relative_path")
    risks = ["prior_failure_pattern:" + pattern for pattern in failures][:8]
    value = {"contract": CONTEXT_CONTRACT, "query_text": query_text, "experience_references": [{"experience_id": match["experience_id"], "similarity_score": match["similarity_score"], "outcome": match["outcome"]} for match in matches], "successful_patterns": successful, "failure_patterns": failures, "recommended_validations": sorted(set(validations)), "risk_notes": risks, "matched_tokens": sorted(set(token for match in matches for token in match["matched_tokens"]))[:40]}
    value["context_fingerprint"] = fingerprint(value); return value


__all__ = ["CONTEXT_CONTRACT", "QUERY_CONTRACT", "build_memory_context", "query_relevant_experiences"]
