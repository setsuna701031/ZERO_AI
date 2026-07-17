from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List

from core.runtime.aer_operator_checkpoint import (
    deserialize_operator_checkpoint,
    serialize_operator_checkpoint,
    validate_operator_checkpoint,
)

CHECKPOINT_STORE_DIR_NAME = "operator_checkpoints"
CHECKPOINT_FILE_EXTENSION = ".json"


def checkpoint_store_dir(workspace_root: str) -> str:
    return os.path.abspath(os.path.join(str(workspace_root or ""), CHECKPOINT_STORE_DIR_NAME))


def checkpoint_path(workspace_root: str, checkpoint_id: str) -> str:
    safe_id = _safe_checkpoint_id(checkpoint_id)
    store_dir = checkpoint_store_dir(workspace_root)
    path = os.path.abspath(os.path.join(store_dir, f"{safe_id}{CHECKPOINT_FILE_EXTENSION}"))
    _ensure_inside_store(store_dir, path)
    return path


def save_checkpoint(workspace_root: str, checkpoint: dict) -> dict:
    validation = validate_operator_checkpoint(checkpoint)
    if validation["ok"] is not True:
        return _result(False, "save_checkpoint", errors=list(validation["errors"]))

    checkpoint_id = str(checkpoint.get("checkpoint_id") or "")
    try:
        path = checkpoint_path(workspace_root, checkpoint_id)
    except ValueError as exc:
        return _result(False, "save_checkpoint", errors=[str(exc)])

    store_dir = checkpoint_store_dir(workspace_root)
    os.makedirs(store_dir, exist_ok=True)

    text = serialize_operator_checkpoint(checkpoint)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{checkpoint_id}.",
        suffix=".tmp",
        dir=store_dir,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return _result(True, "save_checkpoint", checkpoint_id=checkpoint_id, path=path)


def load_checkpoint(workspace_root: str, checkpoint_id: str) -> dict:
    try:
        path = checkpoint_path(workspace_root, checkpoint_id)
    except ValueError as exc:
        return _result(False, "load_checkpoint", errors=[str(exc)])

    if not os.path.exists(path):
        return _result(False, "load_checkpoint", checkpoint_id=str(checkpoint_id or ""), errors=["checkpoint not found"])

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = deserialize_operator_checkpoint(handle.read())
    except Exception as exc:
        return _result(False, "load_checkpoint", checkpoint_id=str(checkpoint_id or ""), path=path, errors=[f"invalid checkpoint file: {exc}"])

    validation = validate_operator_checkpoint(payload)
    if validation["ok"] is not True:
        return _result(False, "load_checkpoint", checkpoint_id=str(checkpoint_id or ""), path=path, errors=list(validation["errors"]))

    return _result(True, "load_checkpoint", checkpoint_id=str(checkpoint_id or ""), path=path, checkpoint=payload)


def delete_checkpoint(workspace_root: str, checkpoint_id: str) -> dict:
    try:
        path = checkpoint_path(workspace_root, checkpoint_id)
    except ValueError as exc:
        return _result(False, "delete_checkpoint", errors=[str(exc)])

    if not os.path.exists(path):
        return _result(True, "delete_checkpoint", checkpoint_id=str(checkpoint_id or ""), path=path, deleted=False)

    os.remove(path)
    return _result(True, "delete_checkpoint", checkpoint_id=str(checkpoint_id or ""), path=path, deleted=True)


def list_checkpoints(workspace_root: str) -> List[dict]:
    store_dir = checkpoint_store_dir(workspace_root)
    if not os.path.isdir(store_dir):
        return []

    records: List[dict] = []
    for name in sorted(os.listdir(store_dir)):
        if not name.endswith(CHECKPOINT_FILE_EXTENSION):
            continue
        checkpoint_id = name[: -len(CHECKPOINT_FILE_EXTENSION)]
        loaded = load_checkpoint(workspace_root, checkpoint_id)
        if loaded.get("ok") is True:
            records.append(loaded["checkpoint"])
            continue
        invalid_record = _result(
            False,
            "list_checkpoints",
            checkpoint_id=checkpoint_id,
            path=os.path.abspath(os.path.join(store_dir, name)),
            errors=list(loaded.get("errors") or ["invalid checkpoint file"]),
        )
        records.append(invalid_record)
    return records


def load_checkpoints_for_identity(
    workspace_root: str,
    operator_session_id: str | None = None,
    package_id: str | None = None,
) -> List[dict]:
    records: List[dict] = []
    for checkpoint in list_checkpoints(workspace_root):
        if not _is_checkpoint_payload(checkpoint):
            continue
        if not _matches_identity(
            checkpoint,
            operator_session_id=operator_session_id,
            package_id=package_id,
        ):
            continue
        records.append(checkpoint)
    return records


def latest_checkpoint_for_identity(
    workspace_root: str,
    operator_session_id: str | None = None,
    package_id: str | None = None,
) -> dict:
    records = load_checkpoints_for_identity(
        workspace_root,
        operator_session_id=operator_session_id,
        package_id=package_id,
    )
    if not records:
        return _result(True, "latest_checkpoint_for_identity", found=False)
    return _result(
        True,
        "latest_checkpoint_for_identity",
        checkpoint_id=str(records[-1].get("checkpoint_id") or ""),
        checkpoint=records[-1],
        found=True,
    )


def checkpoint_exists(workspace_root: str, checkpoint_id: str) -> bool:
    try:
        path = checkpoint_path(workspace_root, checkpoint_id)
    except ValueError:
        return False
    return os.path.exists(path)


def _safe_checkpoint_id(checkpoint_id: str) -> str:
    text = str(checkpoint_id or "").strip()
    if not text:
        raise ValueError("checkpoint_id is required")
    if text in {".", ".."}:
        raise ValueError("checkpoint_id must not use path traversal")
    if any(separator and separator in text for separator in (os.sep, os.altsep)):
        raise ValueError("checkpoint_id must not contain path separators")
    normalized = os.path.normpath(text)
    if normalized != text or normalized.startswith(".."):
        raise ValueError("checkpoint_id must not use path traversal")
    return text


def _ensure_inside_store(store_dir: str, path: str) -> None:
    root = os.path.abspath(store_dir)
    target = os.path.abspath(path)
    try:
        common = os.path.commonpath([root, target])
    except ValueError as exc:
        raise ValueError("checkpoint path must stay inside checkpoint store") from exc
    if common != root:
        raise ValueError("checkpoint path must stay inside checkpoint store")


def _is_checkpoint_payload(record: dict) -> bool:
    return isinstance(record, dict) and record.get("contract") and record.get("checkpoint_id")


def _matches_identity(
    checkpoint: dict,
    *,
    operator_session_id: str | None,
    package_id: str | None,
) -> bool:
    if operator_session_id is not None and checkpoint.get("operator_session_id") != str(operator_session_id):
        return False
    if package_id is not None and checkpoint.get("package_id") != str(package_id):
        return False
    return True


def _result(
    ok: bool,
    action: str,
    *,
    checkpoint_id: str = "",
    path: str = "",
    checkpoint: Dict[str, Any] | None = None,
    errors: List[str] | None = None,
    deleted: bool | None = None,
    found: bool | None = None,
) -> dict:
    result: Dict[str, Any] = {
        "ok": ok,
        "action": action,
        "checkpoint_id": checkpoint_id,
        "path": path,
        "errors": list(errors or []),
    }
    if checkpoint is not None:
        result["checkpoint"] = checkpoint
    if deleted is not None:
        result["deleted"] = deleted
    if found is not None:
        result["found"] = found
    return result
