from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.repository_analysis import SUPPORTED_SCHEMAS,analyze_repository
from core.engineering.repository_analysis_closure import validate_repository_analysis_closure
from core.engineering.repository_root_admission import validate_repository_root_admission
from core.engineering.repository_snapshot import validate_repository_snapshot
from core.engineering.repository_topology import validate_repository_topology
from core.engineering.repository_discovery import validate_repository_language_discovery,validate_repository_build_discovery,validate_repository_test_discovery
from core.engineering.repository_dependency_analysis import validate_repository_dependency_analysis
from core.engineering.repository_engineering_inventory import validate_repository_engineering_inventory
from core.engineering.repository_analysis_evidence import validate_repository_analysis_evidence
from core.engineering.repository_analysis_report import validate_repository_analysis_report
VALIDATORS={"zero.engineering.repository_root_admission.v1":validate_repository_root_admission,"zero.engineering.repository_snapshot.v1":validate_repository_snapshot,"zero.engineering.repository_topology.v1":validate_repository_topology,"zero.engineering.repository_language_discovery.v1":validate_repository_language_discovery,"zero.engineering.repository_build_discovery.v1":validate_repository_build_discovery,"zero.engineering.repository_test_discovery.v1":validate_repository_test_discovery,"zero.engineering.repository_dependency_analysis.v1":validate_repository_dependency_analysis,"zero.engineering.repository_engineering_inventory.v1":validate_repository_engineering_inventory,"zero.engineering.repository_analysis_evidence.v1":validate_repository_analysis_evidence,"zero.engineering.repository_analysis_report.v1":validate_repository_analysis_report,"zero.engineering.repository_analysis_closure.v1":validate_repository_analysis_closure}
def _read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);a=s.add_parser("analyze");a.add_argument("json_file");a.add_argument("--repository-root",required=True);a.add_argument("--output")
 for c in ("validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  value=_read(a.json_file)
  if a.command=="analyze":
   result=analyze_repository(value,a.repository_root)
   if a.output:Path(a.output).write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
   return result,0 if result["status"] in {"closed","partial","needs_clarification"} else 1
  schema=value.get("schema") if isinstance(value,dict) else None
  if schema not in SUPPORTED_SCHEMAS:return {"valid":False,"errors":["unsupported_schema"]},1
  checked=VALIDATORS[schema](value)
  if a.command=="validate":return {"valid":checked.valid,"errors":list(checked.errors)},0 if checked.valid else 1
  return {"valid":checked.valid,"schema":schema,"status":value.get("status"),"artifact_id":next((value[k] for k in value if k.endswith("_id") and not k.startswith("source_")),None)},0 if checked.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
