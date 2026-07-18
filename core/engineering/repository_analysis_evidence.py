from __future__ import annotations
from typing import Any
from core.engineering.engineering_intake_common import fingerprint
from core.engineering.repository_analysis_common import ValidationResult,artifact,validate_artifact
SCHEMA="zero.engineering.repository_analysis_evidence.v1";ID_KEY="repository_analysis_evidence_id";PREFIX="engineering-repository-evidence-"
def build_repository_analysis_evidence(artifacts:list[dict[str,Any]])->dict[str,Any]:
 items=[]
 for source in artifacts:
  schema=str(source.get("schema","unknown"));source_path=_source_path(source);observation={"schema":schema,"status":source.get("status"),"summary":_summary(source)}
  material={"evidence_kind":schema.rsplit(".",2)[-2],"source_relative_path":source_path,"source_fingerprint":source.get("fingerprint"),"observation":observation,"confidence_basis":"validated_canonical_artifact"}
  items.append({**material,"evidence_id":"repository-evidence-"+fingerprint(material)[:24]})
 items=sorted(items,key=lambda x:x["evidence_id"]);return artifact(SCHEMA,"indexed",{"evidence_items":items,"source_artifact_fingerprints":sorted(str(a.get("fingerprint")) for a in artifacts)},ID_KEY,PREFIX)
def _source_path(a):
 paths=[]
 for key in ("manifest_paths","configuration_files","entry_point_candidates","test_roots"):
  value=a.get(key,[])
  if isinstance(value,list):paths.extend(x for x in value if isinstance(x,str))
 return sorted(paths)[0] if paths else "repository"
def _summary(a):
 for key in ("entries","languages","detected_build_systems","python_import_edges","core_modules"):
  if isinstance(a.get(key),(list,dict)):return {"metric":key,"count":len(a[key])}
 return {"metric":"artifact","count":1}
def validate_repository_analysis_evidence(v:Any,sources:list[dict[str,Any]]|None=None):
 r=validate_artifact(v,schema=SCHEMA,statuses={"indexed","partial","invalid"},id_key=ID_KEY,prefix=PREFIX,fields={"evidence_items","source_artifact_fingerprints"});e=list(r.errors)
 if isinstance(v,dict):
  ids=[x.get("evidence_id") for x in v.get("evidence_items",[]) if isinstance(x,dict)]
  if ids!=sorted(set(ids)):e.append("invalid_evidence_order")
 if sources is not None and v!=build_repository_analysis_evidence(sources):e.append("source_mismatch")
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["build_repository_analysis_evidence","validate_repository_analysis_evidence"]
