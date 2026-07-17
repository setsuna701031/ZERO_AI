from copy import deepcopy

from core.runtime.runtime_governed_capability_acceptance import run_governed_capability_acceptance, validate_governed_capability_acceptance
from tests.test_runtime_governed_capability_runtime import completed_input


REGRESSIONS = {letter: {"passed": 1, "failed": 0, "skipped": 0, "duration": 0.01, "status": "passed"} for letter in "ABCDEFG"}


def test_acceptance_is_deterministic_detached_and_zero_side_effect(tmp_path):
    (tmp_path / "target.txt").write_text("unchanged", encoding="utf-8")
    source = completed_input(tmp_path)
    first = run_governed_capability_acceptance(source, regressions=REGRESSIONS)
    second = run_governed_capability_acceptance(deepcopy(source), regressions=REGRESSIONS)
    assert first == second
    source["runtime_options"]["dry_run_only"] = False
    assert first["acceptance_status"] == "accepted" and first["merge_ready"] is True
    assert validate_governed_capability_acceptance(first)
    assert all(first[name] is False for name in ("execution_started_claim", "execution_completion_claim",
                                                  "mutation_authorization_claim", "mutation_performed_claim",
                                                  "transaction_committed_claim"))
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "unchanged"


def test_acceptance_without_real_regressions_cannot_claim_merge_ready(tmp_path):
    (tmp_path / "target.txt").touch()
    report = run_governed_capability_acceptance(completed_input(tmp_path))
    assert report["acceptance_status"] == "blocked" and report["merge_ready"] is False
