import ast
from copy import deepcopy
from pathlib import Path

from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_strategy_selector import select_capability_strategy
from core.runtime.runtime_capability_strategy_validation import validate_capability_strategy


ROOT = Path(__file__).resolve().parents[1]


def test_selected_strategy_valid_and_fingerprint_mismatch_rejected():
    strategy = select_capability_strategy(RuntimeCapabilityDetector([]).detect()).to_dict()
    assert validate_capability_strategy(strategy).valid
    changed = deepcopy(strategy); changed["recommended_mode"] = "offline_safe"
    assert "fingerprint_mismatch" in validate_capability_strategy(changed).errors


def test_duplicate_preferences_and_non_json_values_rejected():
    strategy = select_capability_strategy(RuntimeCapabilityDetector([]).detect()).to_dict()
    strategy["tool_preferences"] = [{"name": "git"}, {"name": "git"}]
    assert "duplicate_entries:tool_preferences" in validate_capability_strategy(strategy).errors
    strategy["constraints"] = [{"code": {"bad"}}]
    assert "not_json_serializable" in validate_capability_strategy(strategy).errors


def test_sensitive_or_unexpected_fields_are_rejected():
    strategy = select_capability_strategy(RuntimeCapabilityDetector([]).detect()).to_dict()
    strategy["credential"] = "secret"
    result = validate_capability_strategy(strategy)
    assert "unexpected:credential" in result.errors
    assert "sensitive_field" in result.errors


def test_strategy_domain_is_pure_import_and_call_boundary():
    files = [ROOT / "core/runtime/runtime_capability_strategy.py", ROOT / "core/runtime/runtime_capability_strategy_selector.py", ROOT / "core/runtime/runtime_capability_strategy_validation.py", ROOT / "cli/zero_capability_strategy.py"]
    forbidden = ("executor", "scheduler", "subprocess", "mutation", "approval", "authorization", "mission", "operator")
    violations = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        for name in imports:
            if any(term in name.casefold() for term in forbidden): violations.append((path.name, name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess": violations.append((path.name, "subprocess call"))
    assert not violations
