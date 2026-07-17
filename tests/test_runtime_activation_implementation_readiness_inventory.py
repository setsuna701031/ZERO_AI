from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/runtime_activation_implementation_readiness_inventory.md",
    ROOT / "docs/runtime_activation_implementation_touchpoint_matrix.md",
    ROOT / "docs/runtime_activation_implementation_bypass_risk_inventory.md",
    ROOT / "docs/runtime_activation_implementation_adapter_gap_inventory.md",
    ROOT / "docs/runtime_activation_implementation_test_gap_inventory.md",
    ROOT / "docs/runtime_activation_implementation_no_go_inventory.md",
    ROOT / "docs/runtime_activation_implementation_readiness_seal.md",
)

REQUIRED_PHRASES = (
    "implementation readiness inventory only",
    "no runtime wiring created",
    "no adapter created",
    "no activation enabled",
    "no dispatch path created",
    "no executor path created",
    "no mutation path created",
    "runtime owner entrypoint identified before wiring",
    "scheduler touch point identified before wiring",
    "executor touch point identified before wiring",
    "mutation owner identified before wiring",
    "recovery remains review restore block only",
    "missing adapter contract means NO-GO",
    "missing focused runtime tests means NO-GO",
    "unresolved bypass risk means NO-GO",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_implementation_readiness_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_implementation_readiness_docs_contain_required_phrases():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text
