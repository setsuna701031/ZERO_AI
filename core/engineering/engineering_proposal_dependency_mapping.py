from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import ValidationResult,fingerprint,proposal_artifact,stable_proposal_id,validate_proposal_artifact
SCHEMA="zero.engineering.proposal_dependency_mapping.v1";ID_KEY="proposal_dependency_mapping_id";PREFIX="engineering-proposal-dependencies-";FIELDS={"proposed_change_nodes","dependency_edges","planning_work_item_linkage","ordering_constraints","parallelizable_groups","blocked_changes","unresolved_dependencies","cycle_status","rationale"}
def build_engineering_proposal_dependency_mapping(changes:list[Mapping[str,Any]],edges:list[Mapping[str,str]]|None=None)->dict[str,Any]:
 nodes=sorted(x.get("proposed_change_id") for x in changes);links={x["proposed_change_id"]:x["work_item_id"] for x in changes};pairs=[]
 for edge in edges or []:
  a=edge.get("predecessor");b=edge.get("successor")
  if a not in nodes or b not in nodes:raise ValueError("missing_dependency_node")
  pairs.append({"predecessor":a,"successor":b,"evidence_references":sorted(set(edge.get("evidence_references",[])))})
 pairs=sorted(pairs,key=lambda x:(x["predecessor"],x["successor"]));incoming={n:set() for n in nodes}
 for x in pairs:incoming[x["successor"]].add(x["predecessor"])
 remaining=set(nodes);order=[];groups=[]
 while remaining:
  ready=sorted(n for n in remaining if not(incoming[n]&remaining))
  if not ready:break
  groups.append(ready);order.extend(ready);remaining-=set(ready)
 cycle=bool(remaining);material={"proposed_change_nodes":nodes,"dependency_edges":pairs,"planning_work_item_linkage":links,"ordering_constraints":order if not cycle else [],"parallelizable_groups":groups if not cycle else [],"blocked_changes":sorted(remaining),"unresolved_dependencies":sorted(remaining),"cycle_status":"cycle_detected" if cycle else "acyclic","rationale":"Proposal ordering preserves sealed plan linkage and is not an execution schedule"}
 return proposal_artifact(SCHEMA,"blocked" if cycle else "mapped",material,ID_KEY,PREFIX)
def validate_engineering_proposal_dependency_mapping(v:Any)->ValidationResult:
 return validate_proposal_artifact(v,schema=SCHEMA,statuses={"mapped","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
build_proposal_dependency_mapping=build_engineering_proposal_dependency_mapping
__all__=["build_engineering_proposal_dependency_mapping","build_proposal_dependency_mapping","validate_engineering_proposal_dependency_mapping"]
