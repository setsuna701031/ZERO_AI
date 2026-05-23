from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


_RUNTIME_SNAPSHOT_ROOT = (
    Path(__file__).resolve().parents[3]
    / "workspace"
    / "runtime_snapshot"
)


def _load_snapshot_file(filename: str) -> Dict[str, Any]:
    path = _RUNTIME_SNAPSHOT_ROOT / filename

    if not path.exists():
        return {
            "loaded": False,
            "filename": filename,
            "reason": "snapshot file not found",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        return {
            "loaded": True,
            "filename": filename,
            "path": str(path),
            "data": data,
        }

    except Exception as exc:
        return {
            "loaded": False,
            "filename": filename,
            "path": str(path),
            "reason": str(exc),
        }


def load_runtime_state_snapshot() -> Dict[str, Any]:
    return _load_snapshot_file("runtime_state_snapshot.json")


def load_mutation_runtime_transition() -> Dict[str, Any]:
    return _load_snapshot_file("mutation_runtime_transition.json")


def load_mutation_proposal_contract() -> Dict[str, Any]:
    return _load_snapshot_file("mutation_proposal_contract.json")


def load_runtime_awareness_bundle() -> Dict[str, Any]:
    runtime_state = load_runtime_state_snapshot()
    mutation_transition = load_mutation_runtime_transition()
    mutation_contract = load_mutation_proposal_contract()

    return {
        "awareness_type": "runtime_awareness_bundle",
        "runtime_state_snapshot": runtime_state,
        "mutation_runtime_transition": mutation_transition,
        "mutation_proposal_contract": mutation_contract,
        "runtime_awareness_ready": (
            runtime_state.get("loaded", False)
            and mutation_transition.get("loaded", False)
            and mutation_contract.get("loaded", False)
        ),
    }