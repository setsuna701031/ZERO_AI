from __future__ import annotations

from typing import Any, Dict


_EXECUTION_CLASSIFICATION_TABLE = {
    "readonly_execution": {
        "classification": "readonly",
        "risk_level": "low",
        "mutation_capable": False,
        "replay_sensitive": False,
        "governance_critical": False,
    },
    "mutation_runtime": {
        "classification": "mutation",
        "risk_level": "high",
        "mutation_capable": True,
        "replay_sensitive": True,
        "governance_critical": True,
    },
    "patch_apply": {
        "classification": "patch",
        "risk_level": "high",
        "mutation_capable": True,
        "replay_sensitive": True,
        "governance_critical": True,
    },
    "unrestricted_shell": {
        "classification": "shell",
        "risk_level": "critical",
        "mutation_capable": True,
        "replay_sensitive": True,
        "governance_critical": True,
    },
}


def classify_execution_action(action: str) -> Dict[str, Any]:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")

    normalized_action = action.strip()

    classification = _EXECUTION_CLASSIFICATION_TABLE.get(
        normalized_action,
        {
            "classification": "unknown",
            "risk_level": "unknown",
            "mutation_capable": False,
            "replay_sensitive": True,
            "governance_critical": True,
        },
    )

    return {
        "action": normalized_action,
        **classification,
    }


def build_execution_classification_summary() -> Dict[str, Any]:
    entries = [
        classify_execution_action(action)
        for action in sorted(_EXECUTION_CLASSIFICATION_TABLE.keys())
    ]

    return {
        "classification_layer": "runtime_execution_classification",
        "known_actions": [
            item["action"]
            for item in entries
        ],
        "classifications": entries,
    }