from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "core" / "runtime"

APPROVED_STATE_FILES = {
    RUNTIME_ROOT / "runtime_state_gateway.py",
    RUNTIME_ROOT / "runtime_state_record.py",
    RUNTIME_ROOT / "runtime_state_graph.py",
    RUNTIME_ROOT / "runtime_memory_constitution.py",
    RUNTIME_ROOT / "runtime_session_governance.py",
}

LEGACY_STATE_EXCEPTIONS = set()


class RuntimeStateBypassEnforcementTest(unittest.TestCase):
    def test_runtime_state_records_are_only_created_by_gateway(self) -> None:
        violations: list[str] = []
        for path in RUNTIME_ROOT.rglob("*.py"):
            if path in APPROVED_STATE_FILES:
                continue
            if not path.name.startswith("runtime_"):
                continue
            for line_no, call_name in self._calls(path):
                if call_name in {
                    "RuntimeStateRecord",
                    "RuntimeMemoryRecord",
                    "RuntimeStateGraphBuilder",
                }:
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}:{call_name}")

        self.assertEqual(violations, [])

    def test_state_gateway_updates_graph_and_memory_constitution(self) -> None:
        source = (RUNTIME_ROOT / "runtime_state_gateway.py").read_text(encoding="utf-8")

        self.assertIn("RuntimeStateRecord", source)
        self.assertIn("RuntimeMemoryRecord", source)
        self.assertIn("memory_constitution.evaluate", source)
        self.assertIn("graph_builder.add_node", source)
        self.assertIn("graph_builder.add_edge", source)
        self.assertIn('"provenance"', source)
        self.assertIn("lineage", source)

    def test_kernel_audit_replay_memory_rules_exist(self) -> None:
        source = (RUNTIME_ROOT / "runtime_memory_constitution.py").read_text(encoding="utf-8")

        self.assertIn("kernel_memory_requires_explicit_authority", source)
        self.assertIn("audit_memory_append_only", source)
        self.assertIn("replay_memory_immutable_after_seal", source)
        self.assertIn("session_memory_owner_bound", source)

    def test_runtime_state_files_do_not_open_new_direct_write_surface(self) -> None:
        violations: list[str] = []
        for path in APPROVED_STATE_FILES:
            for line_no, pattern in self._unsafe_write_calls(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}:{pattern}")

        self.assertEqual(violations, [])

    def test_legacy_state_exception_list_is_zero(self) -> None:
        self.assertEqual(LEGACY_STATE_EXCEPTIONS, set())
        self.assertIn(RUNTIME_ROOT / "runtime_state_gateway.py", APPROVED_STATE_FILES)

    def _calls(self, path: Path) -> list[tuple[int, str]]:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        calls: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = self._call_name(node)
                if name:
                    calls.append((node.lineno, name))
        return calls

    def _unsafe_write_calls(self, path: Path) -> list[tuple[int, str]]:
        hits: list[tuple[int, str]] = []
        for line_no, name in self._calls(path):
            if name in {
                "Path.write_text",
                "Path.write_bytes",
                "write_text",
                "write_bytes",
                "unlink",
                "os.remove",
                "shutil.rmtree",
                "shutil.move",
            }:
                hits.append((line_no, name))
        return hits

    def _call_name(self, node: ast.Call) -> str | None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
        return None


if __name__ == "__main__":
    unittest.main()
