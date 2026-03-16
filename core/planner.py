from __future__ import annotations


class Planner:

    def __init__(self, llm_client):
        self.llm = llm_client

    def create_plan(self, goal: str) -> list[str]:

        prompt = f"""
你是一個軟體工程 AI。

使用者目標:
{goal}

請把任務拆解成步驟。

要求：
- 每行一個步驟
- 不要解釋
- 不要編號
"""

        result = self.llm.generate(prompt)

        steps = []

        for line in result.splitlines():

            step = line.strip()

            if not step:
                continue

            steps.append(step)

        return steps