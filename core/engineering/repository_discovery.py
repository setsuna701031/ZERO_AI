from __future__ import annotations
import json
from pathlib import PurePosixPath,Path
from typing import Any
from core.engineering.repository_analysis_common import AdmittedRepositoryRoot,ValidationResult,artifact,linked,validate_artifact
from core.engineering.repository_snapshot import validate_repository_snapshot
from core.engineering.repository_topology import validate_repository_topology

LANG_SCHEMA="zero.engineering.repository_language_discovery.v1";BUILD_SCHEMA="zero.engineering.repository_build_discovery.v1";TEST_SCHEMA="zero.engineering.repository_test_discovery.v1"
LANG_EXT={".py":"Python",".js":"JavaScript",".jsx":"JavaScript",".ts":"TypeScript",".tsx":"TypeScript",".rs":"Rust",".go":"Go",".java":"Java",".c":"C",".cpp":"C++",".h":"C/C++ Header",".cs":"C#",".sh":"Shell",".ps1":"PowerShell",".html":"HTML",".css":"CSS"}

def build_repository_discoveries(snapshot:dict[str,Any],topology:dict[str,Any],admission:AdmittedRepositoryRoot|None=None):
    valid=validate_repository_snapshot(snapshot).valid and validate_repository_topology(topology,snapshot).valid
    files=[e["relative_path"] for e in snapshot.get("entries",[]) if e.get("entry_kind")=="file"] if valid else []
    counts:dict[str,int]={}; evidence:dict[str,list[str]]={}
    for p in files:
        lang=LANG_EXT.get(PurePosixPath(p).suffix.lower())
        if lang:counts[lang]=counts.get(lang,0)+1;evidence.setdefault(lang,[]).append(p)
    langs=sorted(counts);maximum=max(counts.values(),default=0);primary=sorted(k for k,v in counts.items() if v==maximum and v>=2)
    links={**linked(snapshot,"snapshot","repository_snapshot_id"),**linked(topology,"topology","repository_topology_id")}
    status="discovered" if valid and snapshot.get("status")=="captured" else "partial" if valid else "invalid"
    language=artifact(LANG_SCHEMA,status,{**links,"languages":langs,"file_counts":{k:counts[k] for k in langs},"primary_language_candidates":primary,"evidence_paths":{k:sorted(evidence[k])[:20] for k in langs}},"repository_language_discovery_id","engineering-repository-language-discovery-")
    systems=[]
    mapping={"pyproject.toml":"python-build","setup.py":"setuptools","setup.cfg":"setuptools","package.json":"npm-compatible","cargo.toml":"cargo","go.mod":"go-modules","pom.xml":"maven","build.gradle":"gradle","makefile":"make","cmakelists.txt":"cmake"}
    manifests=topology.get("manifest_files",[]) if valid else []
    for p in manifests:
        name=PurePosixPath(p).name.lower(); system=mapping.get(name,"pip-requirements" if name.startswith("requirements") else None)
        if system:systems.append(system)
    metadata=[]
    if admission and admission.root:
        for p in manifests[:20]:
            metadata.extend(_manifest_metadata(admission.root,p))
    build=artifact(BUILD_SCHEMA,status,{**links,"detected_build_systems":sorted(set(systems)),"manifest_paths":sorted(manifests),"declared_metadata":sorted(metadata,key=lambda x:(x["source_path"],x["key"]))},"repository_build_discovery_id","engineering-repository-build-discovery-")
    test_roots=topology.get("test_roots",[]) if valid else [];test_files=sorted(p for p in files if PurePosixPath(p).name.startswith("test_") or p.startswith(tuple(r+"/" for r in test_roots)))
    configs=sorted(p for p in files if PurePosixPath(p).name.lower() in {"pytest.ini","tox.ini","pyproject.toml","package.json"})
    framework=[];commands=[]
    if any(PurePosixPath(p).name.lower() in {"pytest.ini","conftest.py"} for p in files) or any(PurePosixPath(p).name.startswith("test_") and p.endswith(".py") for p in files):
        framework.append({"framework":"pytest","source_evidence":next((p for p in configs if PurePosixPath(p).name.lower() in {"pytest.ini","pyproject.toml"}),test_files[0] if test_files else "")})
        commands.append({"runner":"python","arguments":["-m","pytest"],"source_evidence":framework[-1]["source_evidence"]})
    test=artifact(TEST_SCHEMA,status,{**links,"test_roots":sorted(test_roots),"test_file_count":len(test_files),"framework_evidence":framework,"configuration_evidence":configs,"test_command_candidates":commands},"repository_test_discovery_id","engineering-repository-test-discovery-")
    return language,build,test

def _manifest_metadata(root:Path,relative:str)->list[dict[str,str]]:
    path=root/relative
    if path.name.lower()!="package.json" or not path.is_file() or path.stat().st_size>65536:return []
    try:data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError):return []
    return [{"source_path":relative,"key":k,"value":str(data[k])[:200]} for k in ("name","version") if isinstance(data.get(k),(str,int,float))]

def _validate(value,schema,id_key,prefix,extra,source_snapshot=None,source_topology=None):
    fields={"source_snapshot_id","source_snapshot_fingerprint","source_topology_id","source_topology_fingerprint",*extra};r=validate_artifact(value,schema=schema,statuses={"discovered","partial","invalid"},id_key=id_key,prefix=prefix,fields=fields);e=list(r.errors)
    if source_snapshot is not None and source_topology is not None:
        expected=build_repository_discoveries(source_snapshot,source_topology)
        index={LANG_SCHEMA:0,BUILD_SCHEMA:1,TEST_SCHEMA:2}[schema]
        # runtime-only manifest metadata is intentionally excluded from source-only rebuild comparison
        candidate=expected[index]
        if schema!=BUILD_SCHEMA and value!=candidate:e.append("source_mismatch")
        elif value.get("source_snapshot_fingerprint")!=source_snapshot.get("fingerprint") or value.get("source_topology_fingerprint")!=source_topology.get("fingerprint"):e.append("source_mismatch")
    return ValidationResult(not e,tuple(dict.fromkeys(e)))
def validate_repository_language_discovery(v,s=None,t=None):return _validate(v,LANG_SCHEMA,"repository_language_discovery_id","engineering-repository-language-discovery-",{"languages","file_counts","primary_language_candidates","evidence_paths"},s,t)
def validate_repository_build_discovery(v,s=None,t=None):return _validate(v,BUILD_SCHEMA,"repository_build_discovery_id","engineering-repository-build-discovery-",{"detected_build_systems","manifest_paths","declared_metadata"},s,t)
def validate_repository_test_discovery(v,s=None,t=None):return _validate(v,TEST_SCHEMA,"repository_test_discovery_id","engineering-repository-test-discovery-",{"test_roots","test_file_count","framework_evidence","configuration_evidence","test_command_candidates"},s,t)
__all__=["build_repository_discoveries","validate_repository_language_discovery","validate_repository_build_discovery","validate_repository_test_discovery"]
