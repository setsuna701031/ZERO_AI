from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = (
    REPO_ROOT / "core" / "runtime",
)

APPROVED_MUTATION_FILES = {
    REPO_ROOT / "core" / "runtime" / "runtime_mutation_gateway.py",
    REPO_ROOT / "core" / "runtime" / "runtime_state_snapshot.py",
}

EXCLUDED_PARTS = {
    "__pycache__",
}

LEGACY_RUNTIME_MUTATION_EXCEPTIONS = set()


class RuntimeMutationBypassEnforcementTest(unittest.TestCase):
    def test_runtime_mutation_governance_files_do_not_bypass_gateway(self) -> None:
        violations: list[str] = []
        for path in self._python_files():
            if path in APPROVED_MUTATION_FILES:
                continue
            if not path.name.startswith("runtime_"):
                continue
            for line_no, pattern in self._unsafe_mutation_calls(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}:{pattern}")

        self.assertEqual(violations, [])

    def test_direct_write_pattern_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "illegal.py"
            path.write_text(
                "from pathlib import Path\n"
                "def bad():\n"
                "    Path('x').write_text('bypass')\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self._unsafe_mutation_calls(path),
                [(3, "Path.write_text")],
            )

    def test_legacy_exception_list_is_zero(self) -> None:
        self.assertEqual(LEGACY_RUNTIME_MUTATION_EXCEPTIONS, set())
        self.assertIn(
            REPO_ROOT / "core" / "runtime" / "runtime_mutation_gateway.py",
            APPROVED_MUTATION_FILES,
        )

    def _python_files(self) -> list[Path]:
        files: list[Path] = []
        for root in SCAN_ROOTS:
            for path in root.rglob("*.py"):
                if any(part in EXCLUDED_PARTS for part in path.parts):
                    continue
                files.append(path)
        return sorted(files)

    def _unsafe_mutation_calls(self, path: Path) -> list[tuple[int, str]]:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        hits: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                hits.extend(self._call_hit(node))
        return hits

    def _call_hit(self, node: ast.Call) -> list[tuple[int, str]]:
        name = self._call_name(node)
        if name in {
            "Path.write_text",
            "Path.write_bytes",
            "os.remove",
            "shutil.rmtree",
            "shutil.move",
        }:
            return [(node.lineno, name)]
        if name in {"write_text", "write_bytes", "unlink"}:
            return [(node.lineno, f"Path.{name}")]
        if name in {"open", "Path.open"} and self._open_write_mode(node):
            return [(node.lineno, f"{name}:write_mode")]
        return []

    def _call_name(self, node: ast.Call) -> str | None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
        return None

    def _open_write_mode(self, node: ast.Call) -> bool:
        mode_node = None
        if len(node.args) >= 2:
            mode_node = node.args[1]
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
                break
        if not isinstance(mode_node, ast.Constant) or not isinstance(mode_node.value, str):
            return False
        return any(flag in mode_node.value for flag in ("w", "a", "x", "+"))


if __name__ == "__main__":
    unittest.main()
