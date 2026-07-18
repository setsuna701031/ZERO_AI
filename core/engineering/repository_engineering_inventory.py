from __future__ import annotations
from typing import Any
from core.engineering.repository_analysis_common import ValidationResult,artifact,linked,validate_artifact
from core.engineering.repository_snapshot import validate_repository_snapshot
from core.engineering.repository_topology import validate_repository_topology
SCHEMA="zero.engineering.repository_engineering_inventory.v1";ID_KEY="repository_engineering_inventory_id";PREFIX="engineering-repository-inventory-"
def build_repository_engineering_inventory(snapshot:dict[str,Any],topology:dict[str,Any])->dict[str,Any]:
 valid=validate_repository_snapshot(snapshot).valid and validate_repository_topology(topology,snapshot).valid;files=sorted(e["relative_path"] for e in snapshot.get("entries",[]) if e.get("entry_kind")=="file") if valid else []
 pick=lambda pred:sorted(p for p in files if pred(p))
 payload={**linked(snapshot,"snapshot","repository_snapshot_id"),**linked(topology,"topology","repository_topology_id"),"core_modules":pick(lambda p:p.startswith("core/") and p.endswith(".py")),"runtime_modules":pick(lambda p:(p.startswith("runtime/") or p.startswith("core/runtime/")) and p.endswith(".py")),"engineering_modules":pick(lambda p:p.startswith("core/engineering/") and p.endswith(".py")),"cli_modules":pick(lambda p:p.startswith("cli/") and p.endswith(".py")),"test_modules":pick(lambda p:(p.startswith("tests/") or p.split("/")[-1].startswith("test_")) and p.endswith(".py")),"validators":pick(lambda p:p.endswith("_validation.py") or p.endswith("_validator.py")),"schemas":pick(lambda p:p.startswith("schemas/") or p.endswith("schema.json")),"entry_point_candidates":topology.get("entry_point_candidates",[]),"documentation":pick(lambda p:p.startswith("docs/") or p.lower().endswith((".md",".rst",".adoc"))),"fixtures":pick(lambda p:"/fixtures/" in "/"+p or p.startswith("fixtures/"))}
 status="inventoried" if valid and snapshot.get("status")=="captured" else "partial" if valid else "invalid";return artifact(SCHEMA,status,payload,ID_KEY,PREFIX)
def validate_repository_engineering_inventory(v:Any,s:Any=None,t:Any=None):
 fields={"source_snapshot_id","source_snapshot_fingerprint","source_topology_id","source_topology_fingerprint","core_modules","runtime_modules","engineering_modules","cli_modules","test_modules","validators","schemas","entry_point_candidates","documentation","fixtures"};r=validate_artifact(v,schema=SCHEMA,statuses={"inventoried","partial","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=fields);e=list(r.errors)
 if s is not None and t is not None and v!=build_repository_engineering_inventory(s,t):e.append("source_mismatch")
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["build_repository_engineering_inventory","validate_repository_engineering_inventory"]
