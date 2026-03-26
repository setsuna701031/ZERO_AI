# zero_v8.py

from llm_client import LocalLLMClient
from router import Router
from tool_registry import ToolRegistry
from agent_loop import AgentLoop


class ZeroV8:
    def __init__(self):
        self.llm_client = LocalLLMClient()
        self.router = Router(llm_client=self.llm_client)
        self.tool_registry = ToolRegistry()

        self.agent = AgentLoop(
            router=self.router,
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            max_steps=6,
            enable_logs=True,
        )

    def chat(self, user_input: str):
        return self.agent.run(user_input)

    def ask(self, user_input: str):
        return self.chat(user_input)


if __name__ == "__main__":
    zero = ZeroV8()

    while True:
        user_text = input("你：").strip()
        if user_text.lower() in ["exit", "quit", "q"]:
            print("ZERO：結束")
            break

        result = zero.chat(user_text)
        print("ZERO：", result.get("answer", "沒有回應"))