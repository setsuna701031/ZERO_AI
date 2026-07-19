from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import fingerprint,stable_id

def build_engineering_dependency_ordering(work_items:list[Mapping[str,Any]],edges:list[Mapping[str,str]]|None=None)->dict[str,Any]:
    nodes=sorted(str(x.get("work_item_id")) for x in work_items); edge_pairs=[]
    for edge in edges or []:
        a=edge.get("predecessor");b=edge.get("successor")
        if a not in nodes or b not in nodes: raise ValueError("missing_dependency_node")
        edge_pairs.append({"predecessor":a,"successor":b})
    edge_pairs=sorted(edge_pairs,key=lambda x:(x["predecessor"],x["successor"]));incoming={n:set() for n in nodes}
    for e in edge_pairs: incoming[e["successor"]].add(e["predecessor"])
    order=[];groups=[];remaining=set(nodes)
    while remaining:
        ready=sorted(n for n in remaining if not (incoming[n]&remaining))
        if not ready: break
        groups.append(ready);order.extend(ready);remaining-=set(ready)
    cycle=bool(remaining); material={"nodes":nodes,"edges":edge_pairs,"execution_order":order if not cycle else [],"parallelizable_groups":groups if not cycle else [],"blocked_items":sorted(remaining),"cycle_status":"cycle_detected" if cycle else "acyclic","rationale":"Deterministic topological ordering; this is not execution scheduling","evidence_references":sorted({r for x in work_items for r in x.get("evidence_references",[])})}
    result={**material,"dependency_graph_id":stable_id("engineering-dependency-graph-",material)};result["fingerprint"]=fingerprint(result);return result

build_dependency_ordering=build_engineering_dependency_ordering
__all__=["build_dependency_ordering","build_engineering_dependency_ordering"]
