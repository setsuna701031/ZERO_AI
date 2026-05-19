from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "core" / "runtime"

APPROVED_PROTECTION_LAYERS = {
    RUNTIME_ROOT / "runtime_authority.py",
    RUNTIME_ROOT / "runtime_capability_scope.py",
    RUNTIME_ROOT / "runtime_kernel_protection.py",
    RUNTIME_ROOT / "runtime_execution_policy.py",
    RUNTIME_ROOT / "runtime_mutation_policy.py",
    RUNTIME_ROOT / "runtime_mutation_gateway.py",
    RUNTIME_ROOT / "runtime_mutation_transaction.py",
    RUNTIME_ROOT / "runtime_state_snapshot.py",
}

LEGACY_PROTECTED_WRITE_EXCEPTIONS = set()


class RuntimeKernelProtectionEnforcementTest(unittest.TestCase):
    def test_mutation_gateway_evaluates_authority_scope_and_protection(self) -> None:
        source = (RUNTIME_ROOT / "runtime_mutation_gateway.py").read_text(encoding="utf-8")

        self.assertIn("authority_evaluator.evaluate", source)
        self.assertIn("capability_evaluator.evaluate", source)
        self.assertIn("kernel_protection.evaluate", source)
        self.assertIn("mutation_policy.evaluate", source)
        self.assertIn("_record_execution_governance", source)

    def test_runtime_execution_policy_requires_identity_and_provenance_metadata(self) -> None:
        source = (RUNTIME_ROOT / "runtime_execution_policy.py").read_text(encoding="utf-8")

        self.assertIn("runtime_authority_metadata_required", source)
        self.assertIn("runtime_provenance_metadata_required", source)
        self.assertIn("runtime_identity", source)
        self.assertIn("provenance", source)

    def test_runtime_mutation_gateway_emits_authority_and_provenance_metadata(self) -> None:
        source = (RUNTIME_ROOT / "runtime_mutation_gateway.py").read_text(encoding="utf-8")

        self.assertIn('"authority"', source)
        self.assertIn('"capability"', source)
        self.assertIn('"protection"', source)
        self.assertIn('"provenance"', source)
        self.assertIn('"runtime_identity"', source)

    def test_direct_protected_zone_writes_are_documented_or_approved(self) -> None:
        violations: list[str] = []
        for path in RUNTIME_ROOT.rglob("*.py"):
            if path in APPROVED_PROTECTION_LAYERS:
                continue
            if not path.name.startswith("runtime_"):
                continue
            for line_no, pattern in self._unsafe_write_calls(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}:{pattern}")

        self.assertEqual(violations, [])

    def test_explicit_legacy_exception_list_is_zero(self) -> None:
        self.assertEqual(LEGACY_PROTECTED_WRITE_EXCEPTIONS, set())
        self.assertIn(RUNTIME_ROOT / "runtime_mutation_gateway.py", APPROVED_PROTECTION_LAYERS)

    def _unsafe_write_calls(self, path: Path) -> list[tuple[int, str]]:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        hits: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = self._call_name(node)
            if name in {
                "Path.write_text",
                "Path.write_bytes",
                "os.remove",
                "shutil.rmtree",
                "shutil.move",
            }:
                hits.append((node.lineno, name))
            elif name in {"write_text", "write_bytes", "unlink"}:
                hits.append((node.lineno, f"Path.{name}"))
            elif name in {"open", "Path.open"} and self._open_write_mode(node):
                hits.append((node.lineno, f"{name}:write_mode"))
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
