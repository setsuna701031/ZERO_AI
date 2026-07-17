from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_repo_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeRepoFileRecord:
    path: str
    size_bytes: int
    sha256: str
    language: str = "text"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "language": self.language,
            "tags": copy.deepcopy(self.tags),
        }


@dataclass(frozen=True)
class RuntimeEngineeringTaskRecord:
    task_id: str
    goal: str
    impacted_files: list[str]
    test_targets: list[str]
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "impacted_files": copy.deepcopy(self.impacted_files),
            "test_targets": copy.deepcopy(self.test_targets),
            "status": self.status,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }


class RuntimeNativeRepoEngineeringSurface:
    """
    Runtime-native engineering surface.

    goal
      -> repo scan
      -> impacted-file analysis
      -> targeted-test planning
      -> mutation preparation
      -> engineering task surface
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.repo_index: dict[str, RuntimeRepoFileRecord] = {}
        self.task_history: list[RuntimeEngineeringTaskRecord] = []

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = "."):
        return cls(workspace_root)

    def scan_repository(
        self,
        *,
        include_suffixes: tuple[str, ...] = (".py", ".md", ".json", ".yaml", ".yml"),
    ) -> dict[str, RuntimeRepoFileRecord]:
        self.repo_index = {}

        for path in self.workspace_root.rglob("*"):
            if not path.is_file():
                continue
            if include_suffixes and path.suffix.lower() not in include_suffixes:
                continue

            try:
                content = path.read_bytes()
            except Exception:
                continue

            rel = str(path.relative_to(self.workspace_root)).replace("\\", "/")
            sha = hashlib.sha256(content).hexdigest()

            language = {
                ".py": "python",
                ".md": "markdown",
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
            }.get(path.suffix.lower(), "text")

            tags = []
            lowered = rel.lower()

            if "test" in lowered:
                tags.append("test")
            if "runtime" in lowered:
                tags.append("runtime")
            if "scheduler" in lowered:
                tags.append("scheduler")
            if "dispatch" in lowered:
                tags.append("dispatch")
            if "mutation" in lowered:
                tags.append("mutation")

            self.repo_index[rel] = RuntimeRepoFileRecord(
                path=rel,
                size_bytes=len(content),
                sha256=sha,
                language=language,
                tags=tags,
            )

        return copy.deepcopy(self.repo_index)

    def impacted_file_analysis(
        self,
        *,
        goal: str,
        keywords: list[str] | None = None,
        limit: int = 20,
    ) -> list[str]:
        if not self.repo_index:
            self.scan_repository()

        goal_lower = goal.lower()
        keywords = [x.lower() for x in (keywords or [])]

        scored: list[tuple[int, str]] = []

        for rel, record in self.repo_index.items():
            score = 0
            rel_lower = rel.lower()

            for token in goal_lower.split():
                if token and token in rel_lower:
                    score += 2

            for token in keywords:
                if token and token in rel_lower:
                    score += 5

            for tag in record.tags:
                if tag in goal_lower:
                    score += 3

            if score > 0:
                scored.append((score, rel))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [item[1] for item in scored[:limit]]

    def targeted_test_plan(
        self,
        *,
        impacted_files: list[str],
    ) -> list[str]:
        targets: list[str] = []

        for item in impacted_files:
            normalized = item.replace("\\", "/")

            if normalized.startswith("core/") and normalized.endswith(".py"):
                stem = Path(normalized).stem
                targets.append(f"tests/test_{stem}_v1.py")

            if "runtime_native" in normalized:
                stem = Path(normalized).stem
                targets.append(f"tests/test_{stem}_seal_v1.py")

        deduped = []
        seen = set()

        for target in targets:
            if target not in seen:
                seen.add(target)
                deduped.append(target)

        return deduped

    def create_engineering_task(
        self,
        *,
        goal: str,
        keywords: list[str] | None = None,
    ) -> RuntimeEngineeringTaskRecord:
        impacted = self.impacted_file_analysis(
            goal=goal,
            keywords=keywords,
        )

        tests = self.targeted_test_plan(
            impacted_files=impacted,
        )

        task = RuntimeEngineeringTaskRecord(
            task_id="runtime-engineering-task-" + stable_repo_fingerprint(
                {
                    "goal": goal,
                    "impacted": impacted,
                    "tests": tests,
                    "sequence": len(self.task_history) + 1,
                }
            )[:16],
            goal=goal,
            impacted_files=impacted,
            test_targets=tests,
            status="planned",
            metadata={
                "keywords": keywords or [],
            },
        )

        self.task_history.append(task)
        return copy.deepcopy(task)

    def engineering_summary(self) -> dict[str, Any]:
        return {
            "ok": True,
            "repo_files": len(self.repo_index),
            "engineering_tasks": len(self.task_history),
            "recent_tasks": [
                task.to_dict()
                for task in self.task_history[-5:]
            ],
        }
