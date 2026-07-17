from __future__ import annotations

from core.system import llm_client
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.external, pytest.mark.llm]




def test_general_generation_budget_prevents_short_artifact_cutoff(monkeypatch) -> None:
    captured: dict[str, object] = {}
    long_response = "project_summary.txt implementation_plan.txt acceptance_checklist.txt " + ("x" * 1200)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"response": long_response}

    class Requests:
        @staticmethod
        def post(url: str, *, json: dict[str, object], timeout: int) -> Response:
            captured.update({"url": url, "json": json, "timeout": timeout})
            return Response()

    monkeypatch.setattr(llm_client, "requests", Requests())
    client = llm_client.LocalLLMClient(
        provider="ollama",
        base_url="http://localhost:11434",
        model="general",
        coder_model="coder",
        timeout=5,
    )

    result = client.generate_general("build requirement artifacts")

    assert result["response"] == long_response
    assert len(result["response"]) > 500
    assert captured["json"]["options"]["num_predict"] == llm_client.GENERAL_GENERATION_NUM_PREDICT
    assert llm_client.GENERAL_GENERATION_NUM_PREDICT >= 1024
