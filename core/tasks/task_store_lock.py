from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class _TaskStoreLock:
    def __init__(self, target_path: str) -> None:
        self.lock_path = os.path.abspath(f"{target_path}.lock")
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._handle = None

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._thread_lock:
            if self._depth == 0:
                self._acquire_os_lock()
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    self._release_os_lock()

    def _acquire_os_lock(self) -> None:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        handle = open(self.lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        self._handle = handle

    def _release_os_lock(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


_LOCKS: dict[str, _TaskStoreLock] = {}
_LOCKS_GUARD = threading.Lock()


def task_store_lock(target_path: str | os.PathLike[str]) -> _TaskStoreLock:
    normalized = os.path.abspath(os.fspath(target_path))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(normalized)
        if lock is None:
            lock = _TaskStoreLock(normalized)
            _LOCKS[normalized] = lock
        return lock


def atomic_write_json(path: str | os.PathLike[str], data: Any, *, default=None) -> None:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, default=default)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


__all__ = ["atomic_write_json", "task_store_lock"]
