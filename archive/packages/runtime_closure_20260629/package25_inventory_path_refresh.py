from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "taskrunner_registry_direct_admission_inventory.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_direct_admission_inventory.py"
REFRESH_REPORT_PATH = ROOT / "taskrunner_registry_direct_admission_inventory_refresh_report.txt"

TEST_SOURCE = 'from __future__ import annotations\n\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nREPORT = ROOT / "taskrunner_registry_direct_admission_inventory.txt"\n\n\ndef test_taskrunner_registry_direct_admission_inventory_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_direct_admission_inventory_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Direct Admission Inventory" in text\n    assert "Direct Registry Call Inventory" in text\n    assert "Package24 Helper Presence" in text\n    assert "Recommended Package26" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_direct_admission_inventory_mentions_package24_helper() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "_zero_taskrunner_registry_admit_aer_closure_v24" in text\n    assert "_aer_registry_admit" in text\n\n\ndef test_taskrunner_registry_direct_admission_inventory_mentions_target() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "core/runtime/task_runner.py" in text\n'


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package25_refresh_backup_{stamp}"))


def main() -> int:
    if not REPORT_PATH.exists():
        raise FileNotFoundError(f"Missing inventory report: {REPORT_PATH}")

    _backup(REPORT_PATH)
    _backup(TEST_PATH)

    report = REPORT_PATH.read_text(encoding="utf-8")
    report = report.replace("core\\runtime\\task_runner.py", "core/runtime/task_runner.py")
    report = report.replace("tests\\test_aer_mainline_closure_seal.py", "tests/test_aer_mainline_closure_seal.py")
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    refresh = "\n".join([
        "Package25 Inventory Path Refresh Report",
        "",
        f"root: {ROOT}",
        f"report: {REPORT_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- normalized inventory report paths to forward slash format",
        "- refreshed inventory test without changing TaskRunner code",
        "",
        "Not touched:",
        "- core/runtime/task_runner.py",
        "- Scheduler",
        "- AgentLoop",
        "- CLI",
        "- RuntimeRouteRegistry",
        "",
        "Validation:",
        "python -m compileall core/runtime tests",
        "python -m pytest tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q",
        "",
    ])
    REFRESH_REPORT_PATH.write_text(refresh, encoding="utf-8", newline="\n")
    print(str(REFRESH_REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
