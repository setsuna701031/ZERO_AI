from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.capabilities import document_flow_orchestrator


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    description: str
    operations: Dict[str, Callable]
    validation_command: str = ""


def _build_registry() -> Dict[str, CapabilitySpec]:
    return {
        "document_flow": CapabilitySpec(
            name="document_flow",
            description=(
                "Document-flow capability wrapper for summary and action-items "
                "tasks through the official task lifecycle."
            ),
            operations={
                "run_summary": document_flow_orchestrator.run_summary,
                "run_action_items": document_flow_orchestrator.run_action_items,
                "run_summary_and_action_items": document_flow_orchestrator.run_summary_and_action_items,
            },
            validation_command="python tests/run_document_flow_orchestrator_smoke.py",
        )
    }


_REGISTRY: Dict[str, CapabilitySpec] = _build_registry()


def list_capabilities() -> List[str]:
    return sorted(_REGISTRY.keys())


def get_capability(name: str) -> Optional[CapabilitySpec]:
    key = str(name or "").strip()
    if not key:
        return None
    return _REGISTRY.get(key)


def get_operation(capability_name: str, operation_name: str) -> Optional[Callable]:
    capability = get_capability(capability_name)
    if capability is None:
        return None

    operation_key = str(operation_name or "").strip()
    if not operation_key:
        return None

    return capability.operations.get(operation_key)


def has_capability(name: str) -> bool:
    return get_capability(name) is not None


def has_operation(capability_name: str, operation_name: str) -> bool:
    return get_operation(capability_name, operation_name) is not None


def describe_capability(name: str) -> Dict[str, object]:
    capability = get_capability(name)
    if capability is None:
        return {
            "found": False,
            "name": str(name or "").strip(),
            "description": "",
            "operations": [],
            "validation_command": "",
        }

    return {
        "found": True,
        "name": capability.name,
        "description": capability.description,
        "operations": sorted(capability.operations.keys()),
        "validation_command": capability.validation_command,
    }


def main() -> int:
    print("[capability-registry] capabilities")
    for name in list_capabilities():
        spec = describe_capability(name)
        print(f"- {spec['name']}")
        print(f"  description: {spec['description']}")
        print(f"  operations: {', '.join(spec['operations'])}")
        print(f"  validation: {spec['validation_command']}")

    document_flow = get_capability("document_flow")
    if document_flow is None:
        print("[capability-registry] FAIL: document_flow missing")
        return 1

    required_operations = [
        "run_summary",
        "run_action_items",
        "run_summary_and_action_items",
    ]

    for operation in required_operations:
        fn = get_operation("document_flow", operation)
        if not callable(fn):
            print(f"[capability-registry] FAIL: document_flow operation missing: {operation}")
            return 1

    print("[capability-registry] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())