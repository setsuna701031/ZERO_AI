from __future__ import annotations
from typing import Any
from core.engineering.engineering_intake_common import identified
from core.engineering.repository_analysis_common import ValidationResult,boundary,linked,validate_artifact
SCHEMA="zero.engineering.repository_analysis_closure.v1";ID_KEY="repository_analysis_closure_id";PREFIX="engineering-repository-closure-"
def build_repository_analysis_closure(request,admission,snapshot,topology,language,build,test,dependency,inventory,evidence,report):
 artifacts=[admission,snapshot,topology,language,build,test,dependency,inventory,evidence,report]
 if any(x.get("status") in {"invalid","rejected"} for x in artifacts):status="rejected"
 elif report.get("next_stage")=="needs_clarification":status="needs_clarification"
 elif any(x.get("status")=="partial" for x in artifacts):status="partial"
 else:status="closed"
 names=[("analysis_request",request,"repository_analysis_request_id"),("root_admission",admission,"repository_root_admission_id"),("snapshot",snapshot,"repository_snapshot_id"),("topology",topology,"repository_topology_id"),("language_discovery",language,"repository_language_discovery_id"),("build_discovery",build,"repository_build_discovery_id"),("test_discovery",test,"repository_test_discovery_id"),("dependency_analysis",dependency,"repository_dependency_analysis_id"),("engineering_inventory",inventory,"repository_engineering_inventory_id"),("analysis_evidence",evidence,"repository_analysis_evidence_id"),("analysis_report",report,"repository_analysis_report_id")]
 payload={"schema":SCHEMA,"status":status,"lineage":{k:linked(v,k,i) for k,v,i in names},"report":report,"boundary":boundary(completed=status=="closed")}
 return identified(payload,ID_KEY,PREFIX)
def validate_repository_analysis_closure(v:Any):
 r=validate_artifact(v,schema=SCHEMA,statuses={"closed","partial","needs_clarification","rejected","invalid"},id_key=ID_KEY,prefix=PREFIX,fields={"lineage","report"},completed=isinstance(v,dict) and v.get("status")=="closed");e=list(r.errors)
 if isinstance(v,dict):
  report=v.get("report")
  if not isinstance(report,dict) or report.get("fingerprint")!=v.get("lineage",{}).get("analysis_report",{}).get("source_analysis_report_fingerprint"):e.append("report_lineage_mismatch")
  else:
   from core.engineering.repository_analysis_report import validate_repository_analysis_report
   if not validate_repository_analysis_report(report).valid:e.append("invalid_nested_report")
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["build_repository_analysis_closure","validate_repository_analysis_closure"]
