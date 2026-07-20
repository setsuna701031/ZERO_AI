from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any, Mapping
from .engineering_task_orchestration_validation import canonical_json, validate_state

class TaskPersistenceError(ValueError): pass

def task_dir(repo_root: str|Path, task_id:str)->Path:
    if '/' in task_id or '..' in task_id: raise TaskPersistenceError('unsafe_task_id')
    root=Path(repo_root).resolve(); base=(root/'.zero'/'engineering'/'tasks').resolve(); path=(base/task_id).resolve()
    if not str(path).startswith(str(base)): raise TaskPersistenceError('path_escape')
    return path

def state_path(repo_root: str|Path, task_id:str)->Path: return task_dir(repo_root, task_id)/'state.json'

def save_state(repo_root: str|Path, state:Mapping[str,Any])->dict[str,Any]:
    v=validate_state(state)
    if not v.valid: raise TaskPersistenceError(','.join(v.errors))
    d=task_dir(repo_root, str(state['task_id'])); d.mkdir(parents=True, exist_ok=True)
    if d.is_symlink(): raise TaskPersistenceError('symlink_task_dir')
    fd,tmp=tempfile.mkstemp(prefix='.state.', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(canonical_json(state)); f.write('\n')
        os.replace(tmp, d/'state.json')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return dict(state)

def load_state(repo_root: str|Path, task_id:str)->dict[str,Any]:
    p=state_path(repo_root, task_id)
    if p.is_symlink(): raise TaskPersistenceError('symlink_state')
    try: data=json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc: raise TaskPersistenceError('state_load_failed') from exc
    v=validate_state(data)
    if not v.valid: raise TaskPersistenceError(','.join(v.errors))
    return data
