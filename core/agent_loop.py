from core.tool_registry import TOOL_REGISTRY


class AgentLoop:

    def run(self, plan):

        results = []
        observations = []

        steps = []

        # 如果是 multi_step
        if plan.get("action") == "multi_step":
            steps = plan.get("steps", [])

        else:
            steps = [plan]

        step_index = 1

        for step in steps:

            action = step.get("action")

            if action == "reply":

                return {
                    "success": True,
                    "final_answer": step.get("message", ""),
                    "plan": plan,
                    "results": results,
                    "observations": observations
                }

            elif action == "tool":

                tool_name = step.get("tool")
                args = step.get("args", {})

                if tool_name not in TOOL_REGISTRY:

                    return {
                        "success": False,
                        "final_answer": f"Unknown tool: {tool_name}",
                        "plan": plan,
                        "results": results,
                        "observations": observations
                    }

                tool_fn = TOOL_REGISTRY[tool_name]

                result = tool_fn(args)

                results.append({
                    "step": step_index,
                    "tool": tool_name,
                    "args": args,
                    "result": result
                })

                observations.append({
                    "step": step_index,
                    "tool": tool_name,
                    "observation": result
                })

                step_index += 1

            else:

                return {
                    "success": False,
                    "final_answer": f"Unknown action: {action}",
                    "plan": plan,
                    "results": results,
                    "observations": observations
                }

        # 最後一個結果當 final_answer

        final_answer = ""

        if results:
            last = results[-1]["result"]
            final_answer = str(last.get("data", last))

        return {
            "success": True,
            "final_answer": final_answer,
            "plan": plan,
            "results": results,
            "observations": observations
        }