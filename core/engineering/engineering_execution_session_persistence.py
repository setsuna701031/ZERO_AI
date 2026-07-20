from __future__ import annotations
from pathlib import Path
import tempfile
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import canonical_json
from core.engineering.engineering_execution_session import validate_engineering_execution_session
from core.engineering.engineering_execution_controller import resume_execution_session

SECRET_WORDS=("secret","payload","content","command")
def _bounded_value(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {k:_bounded_value(x) for k,x in v.items() if not any(w in str(k).lower() for w in SECRET_WORDS)}
    if isinstance(v, list):
        return [_bounded_value(x) for x in v]
    return v
def _bounded(s: Mapping[str, Any]) -> dict[str, Any]:
    return dict(_bounded_value(s))
def persist_execution_session(session: Mapping[str, Any], path: str|Path) -> dict[str, Any]:
    data=_bounded(session)
    from core.engineering.engineering_execution_session import seal_session
    data=seal_session(data)
    r=validate_engineering_execution_session(data)
    if not r["valid"]: raise ValueError("invalid_session")
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(p.parent), delete=False) as f:
        f.write(canonical_json(data)); tmp=Path(f.name)
    tmp.replace(p); return data
def load_execution_session(path: str|Path) -> dict[str, Any]:
    import json
    data=json.loads(Path(path).read_text(encoding="utf-8")); r=validate_engineering_execution_session(data)
    if not r["valid"]: raise ValueError("corrupted_session:"+",".join(r["errors"]))
    return data
def resume_persisted_execution_session(path: str|Path) -> dict[str, Any]:
    return resume_execution_session(load_execution_session(path))
