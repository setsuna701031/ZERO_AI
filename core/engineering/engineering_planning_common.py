from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass as _dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

FORBIDDEN_AUTHORITIES = frozenset({"execution_authority", "mutation_authority", "approval_authority", "authorization_authority", "proposal"})
ALLOWED_ACTIONS = ("analyze", "design", "document", "implement", "inspect", "validate")
FORBIDDEN_ACTIONS = ("approval granting", "authorization granting", "direct mutation without later governed authorization", "scope expansion")


def planning_boundary() -> dict[str, bool]:
    return {"sealed": True, "read_only": True, "planning_completed": False,
            "proposal_created": False, "repository_modified": False,
            "execution_started": False, "mutation_allowed": False,
            "approval_granted": False, "authorization_granted": False,
            "authority_granted": False, "scope_expansion": False}


def planning_artifact(schema: str, status: str, payload: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    return identified({"schema": schema, "status": status, **deepcopy(dict(payload)), "boundary": planning_boundary()}, id_key, prefix)


def validate_planning_artifact(value: Any, *, schema: str, statuses: set[str], id_key: str,
                               prefix: str, fields: set[str]) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    required = {"schema", "status", id_key, "fingerprint", "boundary", *fields}
    errors = [f"missing:{key}" for key in sorted(required - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != schema or value.get("status") not in statuses:
        errors.append("invalid_contract")
    if value.get("boundary") != planning_boundary():
        errors.append("unsafe_boundary")
    try:
        if not identity_valid(value, id_key, prefix): errors.append("identity_mismatch")
    except (TypeError, ValueError): errors.append("identity_mismatch")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def stable_id(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + fingerprint(value)[:24]


def immutable(value: Any) -> Any: return deepcopy(value)
def stable_strings(values: Any) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values): raise ValueError("invalid_string_list")
    return sorted(set(values))

MAX_TEXT = 512
MAX_SUMMARY = 640
SHA256_HEX = set('0123456789abcdef')
AUTHORITY_FIELDS = {'approval_granted','authorization_granted','token_issued','mutation_authorized','execution_authority','mutation_authority','verification_authority','approval_authority','authorization_authority','token_authority','executor_handoff','transaction_package','prepared_mutation_package','authorized_scope'}
EXECUTION_WORDS = ('subprocess','shell=True','os.system','git ','git\t','ssh://','http://','https://','curl ','wget ','python -c','bash ','sh ')

def result(errors: Sequence[str]) -> ValidationResult:
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))

def freeze(d: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(d))

def path_ok(v: Any) -> bool:
    if not isinstance(v, str) or not v or '\\' in v or '\x00' in v or len(v) > 240:
        return False
    p = PurePosixPath(v)
    return not p.is_absolute() and '..' not in p.parts and ':' not in p.parts[0] and '*' not in v

def norm_path(v: Any) -> str:
    if not path_ok(v):
        raise ValueError('unsafe_path')
    return str(PurePosixPath(str(v)))

def norm_paths(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('empty_scope')
    return sorted(dict.fromkeys(norm_path(v) for v in values))

def is_under(path: str, roots: Sequence[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip('/') + '/') for r in roots)

def no_overlap(a: Sequence[str], b: Sequence[str]) -> bool:
    return not any(is_under(x, b) or is_under(y, a) for x in a for y in b)

def subset(child: Sequence[str], parent: Sequence[str]) -> bool:
    return all(is_under(c, parent) for c in child)

def short_text(v: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(v, str):
        raise ValueError('text_not_string')
    s = ' '.join(v.strip().split())
    if not s or len(s) > limit:
        raise ValueError('text_unbounded')
    return s

def fp_ok(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(c in SHA256_HEX for c in v)

def authority_errors(v: Any) -> list[str]:
    errors=[]
    def walk(x: Any, key: str=''):
        if isinstance(x, Mapping):
            for k, val in x.items():
                lk=str(k).lower()
                if lk in AUTHORITY_FIELDS or (lk.endswith('_authority') and val not in (False, 'not_granted', 'planning_only')):
                    errors.append('authority_granting_field')
                walk(val, lk)
        elif isinstance(x, list):
            for y in x: walk(y, key)
        elif isinstance(x, str):
            low=x.lower()
            if any(w in low for w in EXECUTION_WORDS): errors.append('execution_payload')
    walk(v)
    return sorted(set(errors))

def seal(body: dict[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    ident_body={k:v for k,v in body.items() if k not in (id_key,'fingerprint')}
    body[id_key]=prefix+'-'+fingerprint(ident_body)[:24]
    body['fingerprint']=fingerprint({k:v for k,v in body.items() if k!='fingerprint'})
    return body

def id_ok(v: Any, prefix: str) -> bool:
    return isinstance(v, str) and v.startswith(prefix+'-') and len(v) == len(prefix)+25

__all__ = ["ALLOWED_ACTIONS", "FORBIDDEN_ACTIONS", "ValidationResult", "canonical_json", "fingerprint", "immutable", "planning_artifact", "planning_boundary", "stable_id", "stable_strings", "validate_planning_artifact", "MAX_TEXT", "MAX_SUMMARY", "authority_errors", "freeze", "fp_ok", "id_ok", "no_overlap", "norm_path", "norm_paths", "path_ok", "result", "seal", "short_text", "subset"]
