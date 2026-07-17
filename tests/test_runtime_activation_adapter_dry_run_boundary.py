from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    ROOT / "docs/contracts/runtime/runtime_activation_adapter_dry_run_boundary_v1.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_responsibility.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_evidence.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_audit.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_readiness_review.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_no_go_review.md",
    ROOT / "docs/runtime_activation_adapter_dry_run_seal.md",
)

REQUIRED_PHRASES = (
    "dry-run boundary only",
    "dry-run != runtime wiring",
    "dry-run != adapter implementation",
    "dry-run != adapter instance",
    "dry-run != activation enablement",
    "dry-run != scheduler dispatch",
    "dry-run != executor execution",
    "dry-run != mutation permission",
    "dry-run cannot mutate runtime state",
    "dry-run cannot call scheduler",
    "dry-run cannot call executor",
    "dry-run evidence required",
    "dry-run audit required",
    "missing dry-run evidence means NO-GO",
    "missing dry-run audit means NO-GO",
    "lifecycle readiness required",
    "adapter authorization required",
    "mutation remains disabled",
    "no dry-run implementation created",
    "no runtime path created",
    "no implementation files required",
)

VALIDATION_PHRASES = (
    "dry-run is only a validation mode",
    "dry-run creates no runtime effects",
)


def read(path: Path) -> str:
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_runtime_activation_adapter_dry_run_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_runtime_activation_adapter_dry_run_docs_contain_required_invariants():
    for path in DOCS:
        text = read(path)
        for phrase in REQUIRED_PHRASES:
            assert phrase in text


def test_runtime_activation_adapter_dry_run_is_validation_only():
    for path in DOCS:
        text = read(path)
        for phrase in VALIDATION_PHRASES:
            assert phrase in text
