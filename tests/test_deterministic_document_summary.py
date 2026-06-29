from __future__ import annotations

from core.runtime.deterministic_document_summary import (

    deterministic_plain_text_summary,
    install_deterministic_summary_handler,
)
from services.system_boot import boot_system
import pytest

pytestmark = [pytest.mark.llm]



def test_deterministic_plain_text_summary_keeps_short_input() -> None:
    text = "ZERO controlled task real execution test. This file should be summarized."
    assert deterministic_plain_text_summary(text) == text


def test_boot_step_executor_uses_deterministic_summary_fast_path() -> None:
    system = boot_system()

    result = system.step_executor.execute_step(
        {
            "type": "llm",
            "mode": "summary",
            "prompt": "Summarize:\n{{file_content}}",
        },
        task={"task_id": "deterministic_summary_smoke"},
        context={},
        previous_result={
            "content": "ZERO controlled task real execution test. This file should be summarized."
        },
        step_index=1,
        step_count=3,
    )

    assert result.get("ok") is True
    assert result.get("deterministic_summary_fast_path") is True
    assert "ZERO controlled task real execution test" in str(result.get("message") or "")
    assert result.get("error") is None


def test_install_is_idempotent() -> None:
    system = boot_system()
    assert install_deterministic_summary_handler(system.step_executor) is True
    assert install_deterministic_summary_handler(system.step_executor) is True
