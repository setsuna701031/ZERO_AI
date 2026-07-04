from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/contracts/runtime/runtime_activation_adapter_authorization_boundary_v1.md",
    ROOT / "docs/runtime_activation_adapter_authorization_responsibility.md",
    ROOT / "docs/runtime_activation_adapter_authorization_evidence.md",
    ROOT / "docs/runtime_activation_adapter_authorization_audit.md",
    ROOT / "docs/runtime_activation_adapter_authorization_readiness_review.md",
    ROOT / "docs/runtime_activation_adapter_authorization_no_go_review.md",
    ROOT / "docs/runtime_activation_adapter_authorization_seal.md",
)

REQUIRED_PHRASES = (
    "authorization only",
    "authorization is not execution",
    "authorization is not activation",
    "authorization is not runtime wiring",
    "authorization cannot create adapter",
    "authorization cannot call scheduler",
    "authorization cannot call executor",
    "authorization cannot mutate runtime state",
    "admission must happen before authorization",
    "missing admission means NO-GO",
    "missing authority means NO-GO",
    "missing evidence means NO-GO",
    "missing audit means NO-GO",
    "ownership must be explicit",
    "scheduler remains isolated",
    "executor remains isolated",
    "runtime mutation remains disabled",
    "adapter implementation remains absent",
    "authorization cannot create runtime paths",
    "no implementation files required",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_adapter_authorization_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_adapter_authorization_docs_contain_required_invariants():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text
