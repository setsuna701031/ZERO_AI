from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from .engineering_runtime_orchestrator_common import canonical_json, SAFE_RELATIVE
ALLOWED_FILES=("request.json","session.json","phase.json","checkpoints.json","artifact-index.json","result.json","verification.json","evidence.json","closure.json")
def _path(root,session_id,name):
    if name not in ALLOWED_FILES or not SAFE_RELATIVE.fullmatch(session_id): raise ValueError("unsafe_session_store_name")
    return Path(root).resolve()/session_id/name
def write_session_artifact(root,session_id,name,value):
    target=_path(root,session_id,name); target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".runtime-",suffix=".json",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f: f.write(canonical_json(value)+"\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return name
def read_session_artifact(root,session_id,name):
    p=_path(root,session_id,name)
    with p.open("r",encoding="utf-8") as f: value=json.load(f)
    if canonical_json(value)+"\n"!=p.read_text(encoding="utf-8"): raise ValueError("non_canonical_session_json")
    return value
def load_session_store(root,session_id): return {n:read_session_artifact(root,session_id,n) for n in ALLOWED_FILES if _path(root,session_id,n).exists()}
