from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/contracts/runtime/runtime_activation_adapter_admission_boundary_v1.md",
    ROOT / "docs/runtime_activation_adapter_admission_responsibility.md",
    ROOT / "docs/runtime_activation_adapter_admission_evidence.md",
    ROOT / "docs/runtime_activation_adapter_admission_audit.md",
    ROOT / "docs/runtime_activation_adapter_admission_readiness_review.md",
    ROOT / "docs/runtime_activation_adapter_admission_no_go_review.md",
    ROOT / "docs/runtime_activation_adapter_admission_seal.md",
)

REQUIRED_PHRASES = (
    "admission boundary only",
    "admission is not adapter execution",
    "admission is not runtime wiring",
    "admission cannot enable activation",
    "admission cannot create dispatch",
    "admission cannot call scheduler",
    "admission cannot call executor",
    "admission cannot mutate runtime state",
    "adapter ownership required",
    "admission evidence required",
    "admission audit required",
    "missing ownership means NO-GO",
    "missing evidence means NO-GO",
    "missing audit means NO-GO",
    "runtime owner remains authoritative",
    "scheduler remains isolated",
    "executor remains isolated",
    "mutation remains disabled",
    "no adapter implementation created",
    "no implementation files required",
    "no runtime path created",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_adapter_admission_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_adapter_admission_docs_contain_required_invariants():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text
