from pathlib import Path

TARGET = Path("core/tasks/scheduler.py")

KEYWORDS = [
    "tick",
    "loop",
    "step",
    "execute",
    "runtime",
    "trace",
    "replan",
    "repair",
    "status",
]

def test_scheduler_execution_cycle_keywords_exist() -> None:
    text = TARGET.read_text(encoding="utf-8", errors="ignore").lower()

    missing = [k for k in KEYWORDS if k not in text]

    assert not missing, f"missing runtime keywords: {missing}"


def test_scheduler_still_contains_runtime_sections() -> None:
    text = TARGET.read_text(encoding="utf-8", errors="ignore")

    sections = [
        "_trace_",
        "_repair",
        "_replan",
        "_tick",
        "ExecutionTrace",
    ]

    hits = [s for s in sections if s in text]

    assert len(hits) >= 3