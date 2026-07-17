from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def write_plan_graph_journal(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def verify_plan_graph_shape(graph_payload: Dict[str, Any]) -> Dict[str, Any]:
    nodes = graph_payload.get("nodes")
    edges = graph_payload.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return {"ok": False, "reason": "missing_nodes"}
    if not isinstance(edges, list):
        return {"ok": False, "reason": "missing_edges"}

    node_ids = []
    for node in nodes:
        if not isinstance(node, dict):
            return {"ok": False, "reason": "invalid_node"}
        node_id = str(node.get("node_id") or "")
        if not node_id:
            return {"ok": False, "reason": "node_missing_id"}
        node_ids.append(node_id)

    missing_deps: List[str] = []
    node_id_set = set(node_ids)
    for node in nodes:
        for dep in node.get("depends_on", []) if isinstance(node.get("depends_on"), list) else []:
            if str(dep) not in node_id_set:
                missing_deps.append(str(dep))

    if missing_deps:
        return {"ok": False, "reason": "missing_dependencies", "missing_dependencies": missing_deps}

    return {
        "ok": True,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_ids": node_ids,
    }


def collect_verification_edges(graph_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for node in graph_payload.get("nodes", []):
        if not isinstance(node, dict):
            continue
        for verification in node.get("verification", []) if isinstance(node.get("verification"), list) else []:
            edges.append(
                {
                    "node_id": node.get("node_id"),
                    "verification": verification,
                    "targets": node.get("targets", []),
                }
            )
    return edges
