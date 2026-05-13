from __future__ import annotations

import copy
import hashlib
import json
from abc import ABC, abstractmethod

from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle


class RuntimeEvidencePersistenceRejected(RuntimeError):
    pass


class RuntimeEvidenceStore(ABC):
    def __init__(self, store_id: str) -> None:
        self.store_id = self._validate_text("store_id", store_id)

    @abstractmethod
    def save_bundle(self, bundle: RuntimeEvidenceBundle) -> RuntimeEvidenceBundle:
        raise NotImplementedError

    @abstractmethod
    def load_bundle(self, bundle_id: str) -> RuntimeEvidenceBundle:
        raise NotImplementedError

    @abstractmethod
    def has_bundle(self, bundle_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_bundle(self, bundle_id: str) -> RuntimeEvidenceBundle:
        raise NotImplementedError

    @abstractmethod
    def list_bundle_ids(self) -> list[str]:
        raise NotImplementedError

    @property
    @abstractmethod
    def fingerprint(self) -> str:
        raise NotImplementedError

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeEvidencePersistenceRejected(
                f"runtime evidence persistence {field_name} is required"
            )

        return value


class InMemoryRuntimeEvidenceStore(RuntimeEvidenceStore):
    def __init__(self, store_id: str) -> None:
        super().__init__(store_id)
        self._bundles: dict[str, RuntimeEvidenceBundle] = {}
        self._order: list[str] = []

    def save_bundle(self, bundle: RuntimeEvidenceBundle) -> RuntimeEvidenceBundle:
        bundle_id = self._validate_text("bundle_id", getattr(bundle, "bundle_id", None))
        if bundle_id in self._bundles:
            raise RuntimeEvidencePersistenceRejected(
                f"runtime evidence bundle already saved: {bundle_id!r}"
            )

        self._bundles[bundle_id] = copy.deepcopy(bundle)
        self._order.append(bundle_id)
        return copy.deepcopy(self._bundles[bundle_id])

    def load_bundle(self, bundle_id: str) -> RuntimeEvidenceBundle:
        bundle_id = self._validate_text("bundle_id", bundle_id)
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise RuntimeEvidencePersistenceRejected(
                f"runtime evidence bundle does not exist: {bundle_id!r}"
            )

        return copy.deepcopy(bundle)

    def has_bundle(self, bundle_id: str) -> bool:
        bundle_id = self._validate_text("bundle_id", bundle_id)
        return bundle_id in self._bundles

    def delete_bundle(self, bundle_id: str) -> RuntimeEvidenceBundle:
        bundle_id = self._validate_text("bundle_id", bundle_id)
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise RuntimeEvidencePersistenceRejected(
                f"runtime evidence bundle does not exist: {bundle_id!r}"
            )

        del self._bundles[bundle_id]
        self._order.remove(bundle_id)
        return copy.deepcopy(bundle)

    def list_bundle_ids(self) -> list[str]:
        return list(self._order)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            [
                self._bundles[bundle_id].fingerprint
                for bundle_id in self._order
            ],
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
