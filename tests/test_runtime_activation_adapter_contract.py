from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/contracts/runtime/runtime_activation_adapter_contract_v1.md",
    ROOT / "docs/runtime_activation_adapter_responsibility.md",
    ROOT / "docs/runtime_activation_adapter_evidence.md",
    ROOT / "docs/runtime_activation_adapter_audit.md",
    ROOT / "docs/runtime_activation_adapter_readiness_review.md",
    ROOT / "docs/runtime_activation_adapter_no_go_review.md",
    ROOT / "docs/runtime_activation_adapter_seal.md",
)

REQUIRED_PHRASES = (
    "adapter contract only",
    "adapter != runtime wiring",
    "adapter != activation enablement",
    "adapter != execution permission",
    "adapter cannot mutate runtime state",
    "adapter cannot bypass authority chain",
    "adapter cannot create scheduler dispatch",
    "adapter cannot call executor",
    "adapter evidence required",
    "adapter audit required",
    "runtime owner adapter boundary required",
    "scheduler adapter boundary required",
    "executor adapter boundary required",
    "mutation adapter boundary required",
    "missing adapter evidence means NO-GO",
    "missing adapter audit means NO-GO",
    "mutation disabled",
    "no adapter implementation created",
    "no runtime wiring created",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_adapter_contract_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_adapter_contract_docs_contain_required_phrases():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text
