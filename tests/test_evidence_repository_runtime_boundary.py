import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }


def test_runtime_does_not_import_evidence_repository_validator_or_collector() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {
        "core.evidence.evidence_repository",
        "core.evidence.evidence_validator",
        "core.evidence.evidence_collector",
    }
    for path in (root / "core" / "runtime").rglob("*.py"):
        assert not (_imports(path) & forbidden), path


def test_repository_and_chain_do_not_import_runtime_memory_or_goal_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("core/evidence/evidence_repository.py", "core/evidence/evidence_chain.py"):
        path = root / relative
        imports = _imports(path)
        assert not any(name.startswith(("core.runtime", "core.memory")) for name in imports)
        assert "core.goals.goal_repository" not in imports
