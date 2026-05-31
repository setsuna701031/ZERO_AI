from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.runtime_persistence_service import RuntimePersistenceService


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_pytest_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class RuntimePytestTarget:
    test_path: str
    reason: str
    confidence: int = 50
    exists: bool = False
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_path": self.test_path,
            "reason": self.reason,
            "confidence": self.confidence,
            "exists": self.exists,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePytestTarget":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            test_path=str(data.get("test_path") or ""),
            reason=str(data.get("reason") or ""),
            confidence=int(data.get("confidence") or 50),
            exists=bool(data.get("exists", False)),
            source=str(data.get("source") or "heuristic"),
        )


@dataclass(frozen=True)
class RuntimePytestPlan:
    plan_id: str
    impacted_files: list[str]
    targets: list[RuntimePytestTarget] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    fallback_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "impacted_files": copy.deepcopy(self.impacted_files),
            "targets": [target.to_dict() for target in self.targets],
            "commands": copy.deepcopy(self.commands),
            "fallback_commands": copy.deepcopy(self.fallback_commands),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePytestPlan":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            plan_id=str(data.get("plan_id") or ""),
            impacted_files=[str(x) for x in data.get("impacted_files") or []],
            targets=[RuntimePytestTarget.from_dict(x) for x in data.get("targets") or [] if isinstance(x, dict)],
            commands=[str(x) for x in data.get("commands") or []],
            fallback_commands=[str(x) for x in data.get("fallback_commands") or []],
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


class RuntimeNativeTargetedPytestPlannerRejected(RuntimeError):
    pass


class RuntimeNativeTargetedPytestPlanner:
    """
    Runtime-native targeted pytest auto-planner.

    Flow:
      impacted files
        -> direct test mapping
        -> seal test mapping
        -> related runtime keyword tests
        -> command plan
        -> fallback command plan
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        storage_path: str | Path | None = None,
        repo_surface: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_targeted_pytest_planner.json"
        self.repo_surface = repo_surface
        self.persistence_service = RuntimePersistenceService(
            workspace_root=self.workspace_root,
            source="runtime_native_targeted_pytest_planner",
        )
        self._plans: dict[str, RuntimePytestPlan] = {}
        self._order: list[str] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeNativeTargetedPytestPlanner":
        return cls(workspace_root=workspace_root, **kwargs)

    def plan_for_impacted_files(
        self,
        *,
        impacted_files: list[str],
        keywords: list[str] | None = None,
        include_fallback: bool = True,
        plan_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimePytestPlan:
        impacted = [self._normalize_path(x) for x in impacted_files if str(x or "").strip()]
        if not impacted:
            raise RuntimeNativeTargetedPytestPlannerRejected("impacted_files_required")

        if plan_id is None:
            plan_id = "runtime-pytest-plan-" + stable_pytest_fingerprint(
                {
                    "impacted_files": impacted,
                    "keywords": keywords or [],
                    "sequence": len(self._order) + 1,
                }
            )[:16]

        targets = self._select_targets(impacted, keywords=keywords or [])
        commands = [
            f"python -m pytest {target.test_path} -q"
            for target in targets
            if target.exists
        ]

        fallback_commands = []
        if include_fallback:
            fallback_commands = self._fallback_commands(impacted, targets)

        plan = RuntimePytestPlan(
            plan_id=plan_id,
            impacted_files=impacted,
            targets=targets,
            commands=commands,
            fallback_commands=fallback_commands,
            metadata=_copy_dict(metadata),
        )
        self._plans[plan.plan_id] = plan
        self._order.append(plan.plan_id)
        self.save()
        return copy.deepcopy(plan)

    def plan_for_mutation_record(self, mutation_record: Any, *, keywords: list[str] | None = None) -> RuntimePytestPlan:
        payload = mutation_record.to_dict() if hasattr(mutation_record, "to_dict") else copy.deepcopy(mutation_record)
        if not isinstance(payload, dict):
            raise RuntimeNativeTargetedPytestPlannerRejected("mutation_record_must_be_dict")
        impacted = [str(x) for x in payload.get("impacted_files") or []]
        return self.plan_for_impacted_files(
            impacted_files=impacted,
            keywords=keywords,
            metadata={"mutation_id": payload.get("mutation_id", "")},
        )

    def plan_for_patch_record(self, patch_record: Any, *, keywords: list[str] | None = None) -> RuntimePytestPlan:
        payload = patch_record.to_dict() if hasattr(patch_record, "to_dict") else copy.deepcopy(patch_record)
        if not isinstance(payload, dict):
            raise RuntimeNativeTargetedPytestPlannerRejected("patch_record_must_be_dict")
        impacted = [str(x) for x in payload.get("target_files") or []]
        return self.plan_for_impacted_files(
            impacted_files=impacted,
            keywords=keywords,
            metadata={"patch_id": payload.get("patch_id", "")},
        )

    def get_plan(self, plan_id: str) -> RuntimePytestPlan:
        plan_id = str(plan_id or "").strip()
        plan = self._plans.get(plan_id)
        if plan is None:
            raise RuntimeNativeTargetedPytestPlannerRejected(f"pytest plan does not exist: {plan_id!r}")
        return copy.deepcopy(plan)

    def list_plans(self) -> list[RuntimePytestPlan]:
        return [copy.deepcopy(self._plans[item]) for item in self._order if item in self._plans]

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "runtime_phase": "runtime_native_targeted_pytest_planner_health",
            "plans": len(self._plans),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_targeted_pytest_planner",
            "plans": [self._plans[item].to_dict() for item in self._order if item in self._plans],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        if not isinstance(payload, dict):
            return
        self._plans = {}
        self._order = []
        for item in payload.get("plans") or []:
            if isinstance(item, dict):
                plan = RuntimePytestPlan.from_dict(item)
                if plan.plan_id:
                    self._plans[plan.plan_id] = plan
                    self._order.append(plan.plan_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_native_targeted_pytest_planner_save",
            metadata={"runtime_native_targeted_pytest_planner": True},
        )

    def _select_targets(self, impacted: list[str], *, keywords: list[str]) -> list[RuntimePytestTarget]:
        candidates: dict[str, RuntimePytestTarget] = {}

        for path in impacted:
            direct = self._direct_test_for(path)
            if direct:
                self._add_candidate(
                    candidates,
                    direct,
                    reason=f"direct test mapping for {path}",
                    confidence=95,
                    source="direct_mapping",
                )

            seal = self._seal_test_for(path)
            if seal:
                self._add_candidate(
                    candidates,
                    seal,
                    reason=f"seal test mapping for {path}",
                    confidence=85,
                    source="seal_mapping",
                )

            stem = Path(path).stem
            for test in self._tests_matching(stem):
                self._add_candidate(
                    candidates,
                    test,
                    reason=f"test filename matches impacted stem {stem}",
                    confidence=75,
                    source="stem_match",
                )

        for keyword in keywords:
            token = str(keyword or "").strip().lower()
            if not token:
                continue
            for test in self._tests_matching(token):
                self._add_candidate(
                    candidates,
                    test,
                    reason=f"test filename matches keyword {token}",
                    confidence=65,
                    source="keyword_match",
                )

        targets = list(candidates.values())
        targets.sort(key=lambda item: (-item.exists, -item.confidence, item.test_path))
        return targets

    def _add_candidate(
        self,
        candidates: dict[str, RuntimePytestTarget],
        test_path: str,
        *,
        reason: str,
        confidence: int,
        source: str,
    ) -> None:
        normalized = self._normalize_path(test_path)
        exists = (self.workspace_root / normalized).exists()
        previous = candidates.get(normalized)
        target = RuntimePytestTarget(
            test_path=normalized,
            reason=reason,
            confidence=confidence,
            exists=exists,
            source=source,
        )
        if previous is None or target.confidence > previous.confidence:
            candidates[normalized] = target

    def _direct_test_for(self, path: str) -> str:
        normalized = self._normalize_path(path)
        if normalized.startswith("tests/"):
            return normalized
        if normalized.endswith(".py"):
            stem = Path(normalized).stem
            return f"tests/test_{stem}_v1.py"
        return ""

    def _seal_test_for(self, path: str) -> str:
        normalized = self._normalize_path(path)
        if normalized.endswith(".py"):
            stem = Path(normalized).stem
            return f"tests/test_{stem}_seal_v1.py"
        return ""

    def _tests_matching(self, token: str) -> list[str]:
        tests_root = self.workspace_root / "tests"
        if not tests_root.exists():
            return []
        matched = []
        token = token.lower()
        for path in tests_root.rglob("test_*.py"):
            rel = self._normalize_path(str(path.relative_to(self.workspace_root)))
            if token in rel.lower():
                matched.append(rel)
        return matched

    def _fallback_commands(self, impacted: list[str], targets: list[RuntimePytestTarget]) -> list[str]:
        commands = []
        if targets:
            existing = [target.test_path for target in targets if target.exists]
            if existing:
                commands.append("python -m pytest " + " ".join(existing) + " -q")
        if any("runtime" in item for item in impacted):
            commands.append("python -m pytest tests -q")
        if not commands:
            commands.append("python -m pytest -q")
        deduped = []
        seen = set()
        for command in commands:
            if command not in seen:
                seen.add(command)
                deduped.append(command)
        return deduped

    def _normalize_path(self, path: str) -> str:
        text = str(path or "").strip().replace("\\", "/")
        if not text:
            raise RuntimeNativeTargetedPytestPlannerRejected("path_required")
        if text.startswith("./"):
            text = text[2:]
        return text
