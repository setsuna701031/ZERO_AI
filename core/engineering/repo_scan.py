from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".cache",
    "cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".sh",
    ".ps1",
}

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONFIG_EXTENSIONS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
CONFIG_FILENAMES = {
    ".env",
    ".gitignore",
    "dockerfile",
    "makefile",
    "pytest.ini",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
}


@dataclass(frozen=True)
class RepoFileRecord:
    path: str
    classification: str
    suffix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "suffix": self.suffix,
        }


@dataclass(frozen=True)
class RepoScanResult:
    repo_root: str
    scan_id: str
    files: tuple[RepoFileRecord, ...]
    ignored_directories: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "scan_id": self.scan_id,
            "files": [item.to_dict() for item in self.files],
            "ignored_directories": list(self.ignored_directories),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ImpactedFileRecord:
    path: str
    classification: str
    reasons: tuple[str, ...]
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "reasons": list(self.reasons),
            "score": self.score,
        }


@dataclass(frozen=True)
class ImpactedFilePlan:
    plan_id: str
    task: str
    files: tuple[ImpactedFileRecord, ...]
    reasons: tuple[str, ...]
    classification: str
    source_scan_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task": self.task,
            "files": [item.to_dict() for item in self.files],
            "reasons": list(self.reasons),
            "classification": self.classification,
            "source_scan_id": self.source_scan_id,
            "metadata": dict(self.metadata),
        }


def scan_repo(root: str | Path) -> RepoScanResult:
    """Return a deterministic read-only file inventory for a repository root."""

    repo_root = Path(root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"repo_root_not_directory:{repo_root}")

    files: list[RepoFileRecord] = []
    ignored: set[str] = set()

    for directory_text, dirnames, filenames in os.walk(repo_root):
        directory = Path(directory_text)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            if _should_ignore_dir(dirname):
                ignored.add(_relative_path(repo_root, directory / dirname))
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            path = directory / filename
            relative = _relative_path(repo_root, path)
            files.append(
                RepoFileRecord(
                    path=relative,
                    classification=classify_repo_file(relative),
                    suffix=path.suffix.lower(),
                )
            )

    payload = {
        "repo_root": str(repo_root),
        "files": [item.to_dict() for item in files],
        "ignored_directories": sorted(ignored),
    }
    return RepoScanResult(
        repo_root=str(repo_root),
        scan_id="repo-scan-" + _stable_hash(payload)[:16],
        files=tuple(files),
        ignored_directories=tuple(sorted(ignored)),
        metadata=_read_only_metadata(surface="repo_scan"),
    )


def build_impacted_file_plan(
    task: str,
    *,
    repo_root: str | Path | None = None,
    scan: RepoScanResult | None = None,
    max_files: int = 20,
) -> ImpactedFilePlan:
    """Build a conservative read-only impacted file plan from task/path tokens."""

    task_text = str(task or "").strip()
    if not task_text:
        raise ValueError("task_required")
    if scan is None:
        if repo_root is None:
            raise ValueError("repo_root_or_scan_required")
        scan = scan_repo(repo_root)

    task_tokens = _tokens(task_text)
    impacted: list[ImpactedFileRecord] = []

    for record in scan.files:
        score, reasons = _score_file_for_task(record, task_tokens)
        if score <= 0:
            continue
        impacted.append(
            ImpactedFileRecord(
                path=record.path,
                classification=record.classification,
                reasons=tuple(reasons),
                score=score,
            )
        )

    impacted.sort(key=lambda item: (-item.score, item.path))
    impacted = impacted[: max(0, int(max_files))]

    classification = _plan_classification(impacted)
    reasons = _plan_reasons(impacted, task_tokens)
    payload = {
        "task": task_text,
        "source_scan_id": scan.scan_id,
        "files": [item.to_dict() for item in impacted],
        "classification": classification,
    }
    return ImpactedFilePlan(
        plan_id="impacted-file-plan-" + _stable_hash(payload)[:16],
        task=task_text,
        files=tuple(impacted),
        reasons=tuple(reasons),
        classification=classification,
        source_scan_id=scan.scan_id,
        metadata=_read_only_metadata(surface="impacted_file_plan"),
    )


def classify_repo_file(path: str | Path) -> str:
    relative = str(path).replace("\\", "/")
    parts = [part.lower() for part in relative.split("/") if part]
    name = parts[-1] if parts else ""
    suffix = Path(relative).suffix.lower()

    if "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if "docs" in parts or suffix in DOC_EXTENSIONS:
        return "docs"
    if name in CONFIG_FILENAMES or suffix in CONFIG_EXTENSIONS:
        return "config"
    if suffix in SOURCE_EXTENSIONS:
        return "source"
    return "other"


def _score_file_for_task(
    record: RepoFileRecord,
    task_tokens: set[str],
) -> tuple[int, list[str]]:
    path_tokens = _tokens(record.path)
    name_tokens = _tokens(Path(record.path).name)
    matches = sorted(task_tokens.intersection(path_tokens))
    name_matches = sorted(task_tokens.intersection(name_tokens))

    score = 0
    reasons: list[str] = []

    if matches:
        score += len(matches) * 2
        reasons.append("path token match: " + ", ".join(matches))
    if name_matches:
        score += len(name_matches)
        reasons.append("filename token match: " + ", ".join(name_matches))

    classification_token = "doc" if record.classification == "docs" else record.classification
    if classification_token in task_tokens or record.classification in task_tokens:
        score += 2
        reasons.append(f"classification match: {record.classification}")
    if record.classification == "test" and {"test", "tests", "pytest", "coverage"}.intersection(task_tokens):
        score += 2
        reasons.append("test intent match")
    if record.classification == "docs" and {"doc", "docs", "document", "documentation"}.intersection(task_tokens):
        score += 2
        reasons.append("documentation intent match")
    if record.classification == "config" and {"config", "configuration", "settings"}.intersection(task_tokens):
        score += 2
        reasons.append("configuration intent match")

    return score, reasons


def _plan_classification(files: Iterable[ImpactedFileRecord]) -> str:
    classifications = {item.classification for item in files}
    if not classifications:
        return "no_direct_match"
    if len(classifications) == 1:
        return next(iter(classifications))
    return "mixed"


def _plan_reasons(files: Iterable[ImpactedFileRecord], task_tokens: set[str]) -> list[str]:
    file_list = list(files)
    if not file_list:
        return ["no conservative path or classification match found"]
    return [
        "read-only impacted file plan",
        f"matched {len(file_list)} file(s)",
        "task tokens: " + ", ".join(sorted(task_tokens)),
    ]


def _read_only_metadata(*, surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "read_only": True,
        "mutation_allowed": False,
        "execution_allowed": False,
        "patch_apply_allowed": False,
        "autonomous_execution_allowed": False,
    }


def _should_ignore_dir(name: str) -> bool:
    return str(name).strip().lower() in IGNORED_DIR_NAMES


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^A-Za-z0-9]+", str(value).lower())
        if len(token) >= 3
    }


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
