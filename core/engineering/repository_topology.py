from __future__ import annotations
from pathlib import PurePosixPath
from typing import Any
from core.engineering.repository_analysis_common import ValidationResult, artifact, linked, validate_artifact
from core.engineering.repository_snapshot import validate_repository_snapshot

SCHEMA="zero.engineering.repository_topology.v1";ID_KEY="repository_topology_id";PREFIX="engineering-repository-topology-"
MANIFESTS={"pyproject.toml","setup.py","setup.cfg","package.json","cargo.toml","go.mod","pom.xml","build.gradle","makefile","cmakelists.txt"}

def build_repository_topology(snapshot:dict[str,Any])->dict[str,Any]:
    valid=validate_repository_snapshot(snapshot).valid; entries=snapshot.get("entries",[]) if valid else []
    paths=[e["relative_path"] for e in entries if e.get("entry_kind") in {"file","directory"}]
    files=[p for p in paths if next((e for e in entries if e.get("relative_path")==p),{}).get("entry_kind")=="file"]
    dirs=[p for p in paths if p not in files]
    top_dirs=sorted(p for p in dirs if "/" not in p); top_files=sorted(p for p in files if "/" not in p)
    package_roots=sorted({str(PurePosixPath(p).parent) for p in files if PurePosixPath(p).name=="__init__.py" and str(PurePosixPath(p).parent)!="."})
    source_roots=sorted({p for p in top_dirs if p.lower() in {"src","lib","core","app","apps","runtime","services"}})
    test_roots=sorted({p for p in top_dirs if p.lower() in {"test","tests"}})
    cli_roots=sorted({p for p in top_dirs if p.lower() in {"cli","bin"}})
    docs=sorted({p for p in top_dirs if p.lower() in {"doc","docs","documentation"}})
    configs=sorted(p for p in files if PurePosixPath(p).suffix.lower() in {".toml",".yaml",".yml",".ini",".cfg"} or PurePosixPath(p).name.lower() in {".gitignore","dockerfile"})
    manifests=sorted(p for p in files if PurePosixPath(p).name.lower() in MANIFESTS or PurePosixPath(p).name.lower().startswith("requirements") and p.lower().endswith(".txt"))
    entries_out=sorted(p for p in files if p in {"main.py","app.py","zero.py"} or p.startswith("cli/") and p.endswith(".py"))
    status="derived" if valid and snapshot.get("status")=="captured" else "partial" if valid else "invalid"
    return artifact(SCHEMA,status,{**linked(snapshot,"snapshot","repository_snapshot_id"),"top_level_directories":top_dirs,"top_level_files":top_files,"package_roots":package_roots,"source_roots":source_roots,"test_roots":test_roots,"cli_roots":cli_roots,"documentation_roots":docs,"configuration_files":configs,"manifest_files":manifests,"entry_point_candidates":entries_out},ID_KEY,PREFIX)

def validate_repository_topology(value:Any,source_snapshot:Any=None):
    fields={"source_snapshot_id","source_snapshot_fingerprint","top_level_directories","top_level_files","package_roots","source_roots","test_roots","cli_roots","documentation_roots","configuration_files","manifest_files","entry_point_candidates"}
    r=validate_artifact(value,schema=SCHEMA,statuses={"derived","partial","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=fields);e=list(r.errors)
    if isinstance(value,dict) and any(not isinstance(value.get(k),list) or value[k]!=sorted(set(value[k])) for k in fields if not k.startswith("source_")):e.append("unsorted_topology")
    if source_snapshot is not None:
        expected=build_repository_topology(source_snapshot)
        if value!=expected:e.append("source_snapshot_mismatch")
    return ValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["SCHEMA","build_repository_topology","validate_repository_topology"]
