from __future__ import annotations

from pathlib import Path
from typing import Any


RESPONSIBILITY_TERMS = (
    "fallback",
    "legacy",
    "persist",
    "persistence",
    "snapshot",
    "resume",
)

FACADE_COMPATIBILITY_MARKERS = (
    "compat",
    "public",
    "contract",
    "api",
    "overlay",
    "alias",
    "preserve",
)

MIGRATED_HELPER_MARKERS = (
    "apply_autonomous_repair_chain_overlay",
    "apply_boundary_authority_overlay",
    "_zero_safe_public_results_summary",
    "_zero_safe_task_for_snapshot",
)


def classify_scheduler_responsibility_terms(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    items: list[dict[str, Any]] = []
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []

    for line_number, line in enumerate(lines, start=1):
        lowered = line.lower()
        matched_terms = [term for term in RESPONSIBILITY_TERMS if term in lowered]
        if not matched_terms:
            continue
        classification = _classify_line(line)
        items.append(
            {
                "line": line_number,
                "terms": matched_terms,
                "classification": classification,
                "text": line.strip()[:240],
            }
        )

    counts: dict[str, int] = {}
    for item in items:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1

    return {
        "schema": "scheduler_responsibility_slimming_audit.v1",
        "path": str(source_path),
        "count": len(items),
        "classification_counts": counts,
        "items": items,
    }


def _classify_line(line: str) -> str:
    lowered = line.lower()
    if any(marker.lower() in lowered for marker in MIGRATED_HELPER_MARKERS):
        return "migrated_helper_reference"
    if "scheduler_core" in lowered:
        return "migrated_helper_reference"
    if any(marker in lowered for marker in FACADE_COMPATIBILITY_MARKERS):
        return "facade_compatibility"
    if "def " in lowered or "class " in lowered:
        return "helper_logic_to_move"
    return "facade_compatibility"


__all__ = ["classify_scheduler_responsibility_terms"]
