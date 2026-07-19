from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from core.engineering.engineering_intake_common import identified
from core.engineering.repository_root_admission import admit_repository_root,validate_repository_root_admission
from core.engineering.repository_snapshot import build_repository_snapshot,validate_repository_snapshot
from core.engineering.repository_topology import build_repository_topology,validate_repository_topology
from core.engineering.repository_discovery import build_repository_discoveries
from core.engineering.repository_dependency_analysis import build_repository_dependency_analysis
from core.engineering.repository_analysis_closure import validate_repository_analysis_closure
from core.engineering.repository_analysis import analyze_repository
from cli.zero_engineering_repository_analysis import run
from tests.test_engineering_repository_analysis_request import analysis

def fixture(tmp_path:Path):
 tmp_path.mkdir(parents=True,exist_ok=True)
 (tmp_path/"pkg").mkdir();(tmp_path/"pkg"/"__init__.py").write_text("",encoding="utf-8");(tmp_path/"pkg"/"mod.py").write_text("import json\nfrom . import item\n",encoding="utf-8")
 (tmp_path/"tests").mkdir();(tmp_path/"tests"/"test_mod.py").write_text("import pkg.mod\n",encoding="utf-8");(tmp_path/"pytest.ini").write_text("[pytest]\n",encoding="utf-8")
 (tmp_path/"requirements.txt").write_text("pytest==8\n",encoding="utf-8");(tmp_path/".env").write_text("SECRET=x\n",encoding="utf-8");return tmp_path
def test_root_snapshot_deterministic_sensitive_and_topology(tmp_path):
 root=fixture(tmp_path);a=admit_repository_root(root);assert validate_repository_root_admission(a.artifact).valid
 one=build_repository_snapshot(a);two=build_repository_snapshot(a);assert one==two and validate_repository_snapshot(one,a.artifact).valid
 secret=next(x for x in one["entries"] if x["relative_path"]==".env");assert secret["read_status"]=="metadata_only" and secret["sha256"] is None
 t=build_repository_topology(one);assert validate_repository_topology(t,one).valid and t["package_roots"]==["pkg"]
def test_binary_oversized_truncation_and_discovery(tmp_path):
 root=fixture(tmp_path);(root/"blob.bin").write_bytes(b"\0x");(root/"big.txt").write_text("x"*50,encoding="utf-8");a=admit_repository_root(root)
 s=build_repository_snapshot(a,max_entries=4,max_hash_bytes=10);assert s["status"]=="partial" and s["truncated"]
 full=build_repository_snapshot(a);t=build_repository_topology(full);lang,build,test=build_repository_discoveries(full,t,a)
 assert "Python" in lang["languages"] and "pip-requirements" in build["detected_build_systems"] and test["test_file_count"]==1
def test_dependency_ast_never_imports_or_executes(tmp_path):
 root=fixture(tmp_path);marker=root/"ran";(root/"pkg"/"evil.py").write_text(f"open({str(marker)!r},'w').write('x')\nimport os\n",encoding="utf-8")
 a=admit_repository_root(root);s=build_repository_snapshot(a);d=build_repository_dependency_analysis(s,a);assert not marker.exists() and any(x["import_name"]=="os" for x in d["python_import_edges"])
def test_full_closure_and_tamper_rejection(tmp_path):
 closure=analyze_repository(analysis(),fixture(tmp_path));assert closure["status"]=="closed" and validate_repository_analysis_closure(closure).valid
 assert closure["boundary"]["repository_modified"] is False and closure["report"]["next_stage"]=="engineering_planning_pending"
 bad=deepcopy(closure);bad["report"]["repository_summary"]["entry_count"]+=1
 bad=identified({k:v for k,v in bad.items() if k not in {"repository_analysis_closure_id","fingerprint"}},"repository_analysis_closure_id","engineering-repository-closure-")
 assert not validate_repository_analysis_closure(bad).valid
def test_cli_analyze_validate_inspect_and_invalid_root(tmp_path):
 request=tmp_path/"request.json";request.write_text(json.dumps(analysis()),encoding="utf-8");root=fixture(tmp_path/"repo");value,code=run(["analyze",str(request),"--repository-root",str(root)]);assert code==0
 artifact=tmp_path/"closure.json";artifact.write_text(json.dumps(value),encoding="utf-8");assert run(["validate",str(artifact)])[1]==0 and run(["inspect",str(artifact)])[1]==0
 rejected,code=run(["analyze",str(request),"--repository-root",str(tmp_path/"missing")]);assert code==1 and rejected["status"]=="rejected"
