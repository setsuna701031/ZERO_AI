from __future__ import annotations

from pathlib import Path
from typing import Any

from core.engineering.repository_analysis_common import AdmittedRepositoryRoot, artifact, validate_artifact

SCHEMA = "zero.engineering.repository_root_admission.v1"
ID_KEY = "repository_root_admission_id"
PREFIX = "engineering-repository-root-admission-"


def admit_repository_root(repository_root: Any) -> AdmittedRepositoryRoot:
    status, root, reason = "rejected", None, "repository_root_invalid"
    if isinstance(repository_root, (str, Path)) and "\x00" not in str(repository_root):
        try:
            candidate = Path(repository_root).resolve(strict=True)
            if candidate.is_dir():
                next(candidate.iterdir(), None)
                status, root, reason = "admitted", candidate, "repository_root_admitted"
        except (OSError, RuntimeError, ValueError):
            pass
    value = artifact(SCHEMA, status, {"repository_identity_basis": "runtime_root_excluded_from_identity", "reasons": [reason]}, ID_KEY, PREFIX)
    return AdmittedRepositoryRoot(value, root)


def validate_repository_root_admission(value: Any):
    return validate_artifact(value, schema=SCHEMA, statuses={"admitted", "rejected", "invalid"}, id_key=ID_KEY,
                             prefix=PREFIX, fields={"repository_identity_basis", "reasons"})


__all__ = ["SCHEMA", "admit_repository_root", "validate_repository_root_admission"]
