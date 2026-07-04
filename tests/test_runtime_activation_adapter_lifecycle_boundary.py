from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/contracts/runtime/runtime_activation_adapter_lifecycle_boundary_v1.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_responsibility.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_evidence.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_audit.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_readiness_review.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_no_go_review.md",
    ROOT / "docs/runtime_activation_adapter_lifecycle_seal.md",
)

REQUIRED_PHRASES = (
    "lifecycle boundary only",
    "authorization != adapter creation",
    "authorization != adapter initialization",
    "authorization != adapter attachment",
    "adapter creation requires explicit lifecycle decision",
    "adapter initialization requires explicit lifecycle decision",
    "adapter attachment requires explicit lifecycle decision",
    "adapter lifecycle cannot enable activation",
    "adapter lifecycle cannot create dispatch",
    "adapter lifecycle cannot call scheduler",
    "adapter lifecycle cannot call executor",
    "adapter lifecycle cannot mutate runtime state",
    "lifecycle evidence required",
    "lifecycle audit required",
    "missing lifecycle evidence means NO-GO",
    "missing lifecycle audit means NO-GO",
    "scheduler remains isolated",
    "executor remains isolated",
    "mutation remains disabled",
    "no adapter lifecycle implementation created",
    "no runtime path created",
    "no implementation files required",
)

LIFECYCLE_STATES = (
    "proposed",
    "admitted",
    "authorized",
    "created",
    "initialized",
    "attached",
    "retired",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_adapter_lifecycle_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_adapter_lifecycle_docs_contain_required_invariants():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text


def test_runtime_activation_adapter_lifecycle_states_are_documented():
    for path in DOCS:
        text = read(path)
        for state in LIFECYCLE_STATES:
            assert state in text
