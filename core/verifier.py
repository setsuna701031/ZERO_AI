from __future__ import annotations
from typing import Any, Dict


class Verifier:
    """
    ZERO Verifier

    檢查任務是否完成
    """

    def __init__(self, llm_client: Any = None) -> None:
        self.llm_client = llm_client

    def verify(
        self,
        goal: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        檢查 result 是否符合 goal
        """

        if self.llm_client is None:
            return {
                "verified": True,
                "reason": "No LLM verifier available.",
            }

        try:
            prompt = (
                "You are a task verifier.\n"
                "Check whether the task result satisfies the goal.\n\n"
                f"Goal:\n{goal}\n\n"
                f"Result:\n{result}\n\n"
                "Answer only JSON:\n"
                "{ \"verified\": true/false, \"reason\": \"...\" }"
            )

            response = self.llm_client.chat_general(prompt)

            return {
                "verified": True,
                "reason": response,
            }

        except Exception as exc:
            return {
                "verified": False,
                "reason": str(exc),
            }