from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeExecutionScope:
    allowed_surfaces: tuple[str, ...] = ()
    verification_scopes: tuple[str, ...] = ()
    replay_scopes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_surfaces": list(self.allowed_surfaces),
            "verification_scopes": list(self.verification_scopes),
            "replay_scopes": list(self.replay_scopes),
        }


@dataclass(frozen=True)
class RuntimeMutationScope:
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    rollback_scopes: tuple[str, ...] = ()

    def allows(self, path: str) -> bool:
        relative = _normalize(path)
        if any(_in_scope(relative, denied) for denied in self.denied_paths):
            return False
        if not self.allowed_paths:
            return False
        return any(_in_scope(relative, allowed) for allowed in self.allowed_paths)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_paths": list(self.allowed_paths),
            "denied_paths": list(self.denied_paths),
            "rollback_scopes": list(self.rollback_scopes),
        }


@dataclass(frozen=True)
class RuntimeCapabilityNode:
    node_id: str
    capability_type: str
    runtime_surfaces: tuple[str, ...] = ()
    execution_scope: RuntimeExecutionScope = field(default_factory=RuntimeExecutionScope)
    mutation_scope: RuntimeMutationScope = field(default_factory=RuntimeMutationScope)
    inherits: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "capability_type": self.capability_type,
            "runtime_surfaces": list(self.runtime_surfaces),
            "execution_scope": self.execution_scope.to_dict(),
            "mutation_scope": self.mutation_scope.to_dict(),
            "inherits": list(self.inherits),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeCapabilityGraph:
    nodes: dict[str, RuntimeCapabilityNode] = field(default_factory=dict)

    def add_node(self, node: RuntimeCapabilityNode) -> "RuntimeCapabilityGraph":
        return RuntimeCapabilityGraph(nodes={**self.nodes, node.node_id: node})

    def validate_mutation(self, node_id: str, relative_paths: tuple[str, ...]) -> bool:
        node = self._resolve_node(node_id)
        scope = self._merged_mutation_scope(node)
        denied = [path for path in relative_paths if not scope.allows(path)]
        if denied:
            raise PermissionError("runtime_capability_mutation_denied:" + ",".join(sorted(denied)))
        return True

    def validate_execution_surface(self, node_id: str, surface: str) -> bool:
        node = self._resolve_node(node_id)
        scope = self._merged_execution_scope(node)
        if surface not in scope.allowed_surfaces:
            raise PermissionError(f"runtime_capability_execution_denied:{surface}")
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_capability_graph",
            "nodes": {key: value.to_dict() for key, value in sorted(self.nodes.items())},
        }

    def _resolve_node(self, node_id: str) -> RuntimeCapabilityNode:
        if node_id not in self.nodes:
            raise KeyError(f"runtime_capability_node_unknown:{node_id}")
        return self.nodes[node_id]

    def _merged_mutation_scope(self, node: RuntimeCapabilityNode) -> RuntimeMutationScope:
        allowed = list(node.mutation_scope.allowed_paths)
        denied = list(node.mutation_scope.denied_paths)
        rollback = list(node.mutation_scope.rollback_scopes)
        for parent_id in node.inherits:
            parent = self._resolve_node(parent_id)
            parent_scope = self._merged_mutation_scope(parent)
            allowed.extend(parent_scope.allowed_paths)
            denied.extend(parent_scope.denied_paths)
            rollback.extend(parent_scope.rollback_scopes)
        return RuntimeMutationScope(
            allowed_paths=tuple(sorted(set(allowed))),
            denied_paths=tuple(sorted(set(denied))),
            rollback_scopes=tuple(sorted(set(rollback))),
        )

    def _merged_execution_scope(self, node: RuntimeCapabilityNode) -> RuntimeExecutionScope:
        surfaces = list(node.execution_scope.allowed_surfaces)
        verification = list(node.execution_scope.verification_scopes)
        replay = list(node.execution_scope.replay_scopes)
        for parent_id in node.inherits:
            parent_scope = self._merged_execution_scope(self._resolve_node(parent_id))
            surfaces.extend(parent_scope.allowed_surfaces)
            verification.extend(parent_scope.verification_scopes)
            replay.extend(parent_scope.replay_scopes)
        return RuntimeExecutionScope(
            allowed_surfaces=tuple(sorted(set(surfaces))),
            verification_scopes=tuple(sorted(set(verification))),
            replay_scopes=tuple(sorted(set(replay))),
        )


def build_mutation_capability_graph(
    *,
    allowed_paths: tuple[str, ...],
    denied_paths: tuple[str, ...] = (),
    runtime_surfaces: tuple[str, ...] = (),
) -> RuntimeCapabilityGraph:
    base = RuntimeCapabilityNode(
        node_id="runtime:base",
        capability_type="runtime_surface",
        runtime_surfaces=runtime_surfaces,
        execution_scope=RuntimeExecutionScope(
            allowed_surfaces=runtime_surfaces,
            verification_scopes=runtime_surfaces,
            replay_scopes=runtime_surfaces,
        ),
        mutation_scope=RuntimeMutationScope(
            allowed_paths=(),
            denied_paths=denied_paths,
            rollback_scopes=(),
        ),
    )
    mutation = RuntimeCapabilityNode(
        node_id="runtime:governed_mutation",
        capability_type="mutation",
        runtime_surfaces=runtime_surfaces,
        execution_scope=RuntimeExecutionScope(
            allowed_surfaces=runtime_surfaces,
            verification_scopes=runtime_surfaces,
            replay_scopes=runtime_surfaces,
        ),
        mutation_scope=RuntimeMutationScope(
            allowed_paths=allowed_paths,
            denied_paths=denied_paths,
            rollback_scopes=allowed_paths,
        ),
        inherits=("runtime:base",),
    )
    return RuntimeCapabilityGraph().add_node(base).add_node(mutation)


def _normalize(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("/")


def _in_scope(path: str, scope: str) -> bool:
    clean_scope = _normalize(scope).rstrip("/")
    return path == clean_scope or path.startswith(clean_scope + "/")


__all__ = [
    "RuntimeCapabilityGraph",
    "RuntimeCapabilityNode",
    "RuntimeExecutionScope",
    "RuntimeMutationScope",
    "build_mutation_capability_graph",
]
