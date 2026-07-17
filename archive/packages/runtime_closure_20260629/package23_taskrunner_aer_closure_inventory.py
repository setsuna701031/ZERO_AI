from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
AER_TEST_PATH = ROOT / "tests" / "test_aer_mainline_closure_seal.py"
REPORT_PATH = ROOT / "taskrunner_aer_closure_inventory.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_aer_closure_inventory.py"

TEST_SOURCE = 'from __future__ import annotations\n\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nREPORT = ROOT / "taskrunner_aer_closure_inventory.txt"\n\n\ndef test_taskrunner_aer_closure_inventory_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_aer_closure_inventory_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner AER Closure Inventory" in text\n    assert "Target Files" in text\n    assert "Token Inventory" in text\n    assert "Function Inventory" in text\n    assert "Classification" in text\n    assert "Recommended Package24" in text\n\n\ndef test_taskrunner_aer_closure_inventory_mentions_task_runner() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "core/runtime/task_runner.py" in text\n    assert "tests/test_aer_mainline_closure_seal.py" in text\n\n\ndef test_taskrunner_aer_closure_inventory_records_non_mainline_issue_rule() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "Non-mainline issue reporting" in text\n    assert "must be reported explicitly" in text\n'

TOKENS = [
    "run_observer",
    "registry",
    "RuntimeRouteRegistry",
    "execute_owned_step",
    "tick",
    "owned",
    "admit",
    "admitted",
    "authority",
    "evidence",
    "repair",
    "rollback",
    "legacy",
    "compat",
    "compatibility",
    "closure",
]

FUNCTION_KEYWORDS = [
    "run",
    "execute",
    "tick",
    "registry",
    "admit",
    "authority",
    "evidence",
    "repair",
    "rollback",
    "legacy",
    "compat",
]


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package23_backup_{stamp}"))


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _line_hits(lines: list[str], token: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if token in line:
            hits.append((idx, line.rstrip()))
    return hits


def _classify_line(line: str) -> str:
    stripped = line.strip()
    lowered = stripped.lower()
    if stripped.startswith("def "):
        return "function"
    if stripped.startswith("class "):
        return "class"
    if stripped.startswith("#"):
        return "comment"
    if "getattr(" in stripped or "hasattr(" in stripped:
        return "dynamic access"
    if "setattr(" in stripped:
        return "dynamic binding"
    if "registry" in lowered:
        return "registry path"
    if "authority" in lowered:
        return "authority path"
    if "evidence" in lowered:
        return "evidence path"
    if "legacy" in lowered or "compat" in lowered:
        return "legacy/compat path"
    if "repair" in lowered or "rollback" in lowered:
        return "repair/rollback path"
    return "reference"


def _function_inventory(source: str) -> list[str]:
    if not source.strip():
        return ["- task_runner.py missing or empty"]
    tree = ast.parse(source)
    rows: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            lname = name.lower()
            if any(token in lname for token in FUNCTION_KEYWORDS):
                rows.append(f"- line {node.lineno}: {name}")
    return sorted(rows, key=lambda row: int(row.split("line ", 1)[1].split(":", 1)[0]))


def _build_report() -> str:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    task_runner_source = _read(TASK_RUNNER_PATH)
    aer_test_source = _read(AER_TEST_PATH)

    ast.parse(task_runner_source)
    if aer_test_source:
        ast.parse(aer_test_source)

    task_runner_lines = task_runner_source.splitlines()
    aer_test_lines = aer_test_source.splitlines()

    out: list[str] = []
    out.append("TaskRunner AER Closure Inventory")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append("")

    out.append("Target Files")
    out.append(f"- core/runtime/task_runner.py exists: {TASK_RUNNER_PATH.exists()}")
    out.append(f"- tests/test_aer_mainline_closure_seal.py exists: {AER_TEST_PATH.exists()}")
    out.append("")

    out.append("File Sizes")
    out.append(f"- task_runner.py lines: {len(task_runner_lines)}")
    out.append(f"- test_aer_mainline_closure_seal.py lines: {len(aer_test_lines)}")
    out.append("")

    out.append("Token Inventory")
    for token in TOKENS:
        runner_hits = _line_hits(task_runner_lines, token)
        test_hits = _line_hits(aer_test_lines, token)
        out.append(f"- {token}")
        out.append(f"  task_runner count: {len(runner_hits)}")
        for lineno, line in runner_hits[:40]:
            out.append(f"    line {lineno}: [{_classify_line(line)}] {line}")
        if len(runner_hits) > 40:
            out.append(f"    ... {len(runner_hits) - 40} more task_runner hits")
        out.append(f"  aer seal test count: {len(test_hits)}")
        for lineno, line in test_hits[:30]:
            out.append(f"    line {lineno}: {line}")
        if len(test_hits) > 30:
            out.append(f"    ... {len(test_hits) - 30} more test hits")
    out.append("")

    out.append("Function Inventory")
    out.extend(_function_inventory(task_runner_source))
    out.append("")

    out.append("Classification")
    out.append("- current mainline: TaskRunner AER closure, focusing on registry admission for owned step execution and tick paths")
    out.append("- likely closure target: make execute_owned_step and tick paths explicitly registry-admitted through one helper")
    out.append("- likely test driver: tests/test_aer_mainline_closure_seal.py")
    out.append("- avoid scope creep: do not touch Scheduler, AgentLoop, CLI, RuntimeRouteRegistry, or Runtime Native marker blocks")
    out.append("")

    out.append("Recommended Package24")
    out.append("- add a small TaskRunner registry admission helper if missing")
    out.append("- route owned-step execution and tick observer paths through that helper")
    out.append("- add/refresh TaskRunner AER closure seal for helper use and import safety")
    out.append("- keep validation local and targeted first")
    out.append("")

    out.append("Not touched")
    out.append("- Scheduler")
    out.append("- AgentLoop")
    out.append("- CLI")
    out.append("- RuntimeRouteRegistry")
    out.append("- Runtime Native marker chain")
    out.append("")

    out.append("Validation")
    out.append("python -m compileall core/runtime tests")
    out.append("python -m pytest tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
    out.append("")

    out.append("Non-mainline issue reporting")
    out.append("Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.")
    out.append("")

    return "\n".join(out)


def main() -> int:
    _backup(REPORT_PATH)
    _backup(TEST_PATH)

    report = _build_report()
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
