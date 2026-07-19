from __future__ import annotations
import ast,json
from pathlib import PurePosixPath
from typing import Any
from core.engineering.repository_analysis_common import AdmittedRepositoryRoot,MAX_DEPENDENCY_FILES,MAX_DEPENDENCY_FILE_BYTES,ValidationResult,artifact,linked,validate_artifact
from core.engineering.repository_snapshot import validate_repository_snapshot

SCHEMA="zero.engineering.repository_dependency_analysis.v1";ID_KEY="repository_dependency_analysis_id";PREFIX="engineering-repository-dependency-analysis-"
def build_repository_dependency_analysis(snapshot:dict[str,Any],admission:AdmittedRepositoryRoot,*,max_files:int=MAX_DEPENDENCY_FILES,max_file_bytes:int=MAX_DEPENDENCY_FILE_BYTES)->dict[str,Any]:
    valid=validate_repository_snapshot(snapshot).valid and admission.root is not None;limits={"max_files":max(0,min(int(max_files),MAX_DEPENDENCY_FILES)),"max_file_bytes":max(0,min(int(max_file_bytes),MAX_DEPENDENCY_FILE_BYTES)),"view":"static_bounded_dependency_view"}
    py=sorted(e["relative_path"] for e in snapshot.get("entries",[]) if e.get("entry_kind")=="file" and e["relative_path"].endswith(".py")) if valid else []
    selected=py[:limits["max_files"]]; modules={_module(p) for p in py};edges=[];syntax=[];external=set();internal=set();unresolved=[]
    for p in selected:
        entry=next(e for e in snapshot["entries"] if e["relative_path"]==p)
        if entry.get("size_bytes",0)>limits["max_file_bytes"]:unresolved.append({"source_path":p,"reason":"file_limit"});continue
        try:tree=ast.parse((admission.root/p).read_text(encoding="utf-8"))
        except (OSError,UnicodeError,SyntaxError):syntax.append({"source_path":p,"reason":"syntax_or_read_error"});continue
        for node in ast.walk(tree):
            names=[]
            if isinstance(node,ast.Import):names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom):names=[("."*node.level)+(node.module or "")]
            for name in names:
                edge={"source_path":p,"import_name":name,"relative":name.startswith(".")};edges.append(edge)
                top=name.lstrip(".").split(".")[0]
                if top and any(m==top or m.startswith(top+".") for m in modules):internal.add(top)
                elif top:external.add(top)
    declared=_declared(admission, snapshot)
    status="analyzed" if valid and len(py)<=limits["max_files"] and not syntax else "partial" if valid else "invalid"
    return artifact(SCHEMA,status,{**linked(snapshot,"snapshot","repository_snapshot_id"),"declared_dependencies":declared,"python_import_edges":sorted({json.dumps(e,sort_keys=True):e for e in edges}.values(),key=lambda x:(x["source_path"],x["import_name"])),"internal_module_candidates":sorted(internal),"external_import_candidates":sorted(external-internal),"unresolved_imports":sorted(unresolved+syntax,key=lambda x:(x["source_path"],x["reason"])),"analysis_limits":limits},ID_KEY,PREFIX)
def _module(p):
    x=p[:-3].replace("/",".");return x[:-9] if x.endswith(".__init__") else x
def _declared(admission,snapshot):
    result=[]
    for e in snapshot.get("entries",[]):
        p=e.get("relative_path","");name=PurePosixPath(p).name.lower()
        if name.startswith("requirements") and name.endswith(".txt") and e.get("size_bytes",0)<=65536 and e.get("text_kind")=="utf-8":
            try:
                for line in (admission.root/p).read_text(encoding="utf-8").splitlines():
                    line=line.strip()
                    if line and not line.startswith("#") and not line.startswith(("-","http:" ,"https:")):result.append({"name":line[:200],"source_path":p})
            except (OSError,UnicodeError):pass
    return sorted(result,key=lambda x:(x["source_path"],x["name"]))
def validate_repository_dependency_analysis(value:Any,source_snapshot:Any=None):
    fields={"source_snapshot_id","source_snapshot_fingerprint","declared_dependencies","python_import_edges","internal_module_candidates","external_import_candidates","unresolved_imports","analysis_limits"};r=validate_artifact(value,schema=SCHEMA,statuses={"analyzed","partial","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=fields);e=list(r.errors)
    if source_snapshot is not None and value.get("source_snapshot_fingerprint")!=source_snapshot.get("fingerprint"):e.append("source_snapshot_mismatch")
    return ValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["SCHEMA","build_repository_dependency_analysis","validate_repository_dependency_analysis"]
