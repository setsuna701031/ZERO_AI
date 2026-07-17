from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def rel_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def artifact_graph_path(shared_dir: Path) -> Path:
    return shared_dir / "artifact_graph.json"


def artifact_node_type(path: Path, artifact_type: str = "") -> str:
    lowered = path.name.lower()
    artifact_lower = artifact_type.lower()
    if "summary" in lowered or "summary" in artifact_lower:
        return "summary"
    if "report" in lowered or "markdown" in artifact_lower:
        return "report"
    if lowered.endswith(".py"):
        return "python_file"
    if lowered.endswith(".txt"):
        return "text"
    return artifact_lower or "artifact"


def update_artifact_graph(
    *,
    repo_root: Path,
    shared_dir: Path,
    task_id: str,
    goal: str,
    artifact: Dict[str, Any],
) -> Path:
    graph_path = artifact_graph_path(shared_dir)
    artifact_path_raw = artifact.get("artifact_path")
    if not artifact_path_raw:
        return graph_path

    existing = read_json_file(graph_path)
    if not isinstance(existing, dict):
        existing = {"version": 1, "nodes": [], "edges": [], "events": []}

    nodes = existing.get("nodes")
    edges = existing.get("edges")
    events = existing.get("events")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    if not isinstance(events, list):
        events = []

    node_by_path = {
        str(node.get("artifact")): node
        for node in nodes
        if isinstance(node, dict)
    }
    edge_keys = {
        (str(edge.get("from")), str(edge.get("to")), str(edge.get("task_id")))
        for edge in edges
        if isinstance(edge, dict)
    }

    output_path = Path(str(artifact_path_raw))
    output_rel = rel_path(repo_root, output_path)

    input_path_raw = artifact.get("input_path")
    input_rel: Optional[str] = None
    if input_path_raw:
        input_rel = rel_path(repo_root, Path(str(input_path_raw)))

    now = time.time()
    artifact_type = str(artifact.get("artifact_type") or "")

    if input_rel and input_rel not in node_by_path:
        input_node = {
            "artifact": input_rel,
            "type": "input",
            "first_seen_at": now,
            "last_seen_at": now,
        }
        nodes.append(input_node)
        node_by_path[input_rel] = input_node
    elif input_rel:
        node_by_path[input_rel]["last_seen_at"] = now

    if output_rel not in node_by_path:
        output_node = {
            "artifact": output_rel,
            "type": artifact_node_type(output_path, artifact_type),
            "artifact_type": artifact_type,
            "first_seen_at": now,
            "last_seen_at": now,
            "producer_task_id": task_id,
        }
        nodes.append(output_node)
        node_by_path[output_rel] = output_node
    else:
        node_by_path[output_rel]["last_seen_at"] = now
        node_by_path[output_rel]["artifact_type"] = artifact_type
        node_by_path[output_rel]["producer_task_id"] = task_id

    if input_rel:
        edge_key = (input_rel, output_rel, task_id)
        if edge_key not in edge_keys:
            edges.append(
                {
                    "from": input_rel,
                    "to": output_rel,
                    "task_id": task_id,
                    "operation": artifact_type or "artifact_write",
                    "created_at": now,
                }
            )

    events.append(
        {
            "task_id": task_id,
            "goal": goal,
            "input": input_rel,
            "output": output_rel,
            "artifact_type": artifact_type,
            "created_at": now,
        }
    )

    existing["version"] = 1
    existing["updated_at"] = now
    existing["nodes"] = nodes
    existing["edges"] = edges
    existing["events"] = events[-200:]
    write_json_file(graph_path, existing)
    return graph_path


def format_artifact_graph(shared_dir: Path) -> str:
    graph = read_json_file(artifact_graph_path(shared_dir))
    if not isinstance(graph, dict):
        return "artifact_graph.json not found."

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    events = graph.get("events")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    if not isinstance(events, list):
        events = []

    lines: List[str] = []
    lines.append("ZERO Artifact Graph")
    lines.append("")
    lines.append(f"nodes: {len(nodes)}")
    lines.append(f"edges: {len(edges)}")
    lines.append(f"events: {len(events)}")
    lines.append("")

    if edges:
        lines.append("Edges:")
        for edge in edges[-30:]:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            op = str(edge.get("operation") or "artifact_write")
            task_id = str(edge.get("task_id") or "")
            lines.append(f"- {source} -> {target} [{op}] {task_id}")
        lines.append("")

    if nodes:
        lines.append("Nodes:")
        for node in nodes[-30:]:
            if not isinstance(node, dict):
                continue
            artifact = str(node.get("artifact") or "")
            node_type = str(node.get("type") or "artifact")
            producer = str(node.get("producer_task_id") or "")
            if producer:
                lines.append(f"- {artifact} ({node_type}) producer={producer}")
            else:
                lines.append(f"- {artifact} ({node_type})")

    return "\n".join(lines)
