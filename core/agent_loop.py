import json
import re
from core.planner import create_plan
from core.executor import execute_plan
from core.llm_client import ask_local_llm


def _extract_json_block(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None

    if text.startswith("{") and text.endswith("}"):
        return text

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0).strip()

    return None


def _assess_completion(goal: str, execution_result: dict, model_name: str = "llama3.1") -> dict:
    prompt = f"""
You are an AI task judge.

You must decide whether the user's goal has been completed based on the execution result.

Return JSON only.
Do not add markdown.
Do not explain outside JSON.

Format:
{{
  "done": true,
  "reason": "short reason",
  "next_goal": ""
}}

If not done, set:
- "done": false
- "reason": why it is not complete
- "next_goal": the next concrete goal for the next planning iteration

User goal:
{goal}

Execution result:
{json.dumps(execution_result, ensure_ascii=False)}
"""

    llm_result = ask_local_llm(prompt, model_name=model_name)

    if not llm_result.get("success"):
        return {
            "success": False,
            "error": llm_result.get("message", "judge llm failed"),
            "details": llm_result.get("details", "")
        }

    raw_text = llm_result.get("answer", "").strip()
    json_text = _extract_json_block(raw_text)

    if not json_text:
        return {
            "success": False,
            "error": "judge returned invalid JSON",
            "raw": raw_text
        }

    try:
        data = json.loads(json_text)
    except Exception:
        return {
            "success": False,
            "error": "judge returned invalid JSON",
            "raw": raw_text
        }

    done = bool(data.get("done", False))
    reason = str(data.get("reason", "")).strip()
    next_goal = str(data.get("next_goal", "")).strip()

    return {
        "success": True,
        "done": done,
        "reason": reason,
        "next_goal": next_goal
    }


def run_agent_loop(
    goal: str,
    max_iterations: int = 3,
    planner_model: str = "zero_general:latest",
    judge_model: str = "llama3.1",
) -> dict:
    goal = (goal or "").strip()

    if not goal:
        return {
            "success": False,
            "error": "goal is empty"
        }

    if max_iterations <= 0:
        max_iterations = 1

    original_goal = goal
    current_goal = goal
    history = []

    for iteration in range(1, max_iterations + 1):
        plan_result = create_plan(current_goal, model_name=planner_model)
        if not plan_result.get("success"):
            return {
                "success": False,
                "mode": "agent",
                "error": "planner failed",
                "iteration": iteration,
                "current_goal": current_goal,
                "history": history,
                "planner_result": plan_result,
            }

        plan = plan_result.get("plan", {})
        execute_result = execute_plan(plan)

        iteration_record = {
            "iteration": iteration,
            "goal": current_goal,
            "plan": plan,
            "execute_result": execute_result,
        }

        history.append(iteration_record)

        if not execute_result.get("success"):
            return {
                "success": False,
                "mode": "agent",
                "error": "executor failed",
                "iteration": iteration,
                "current_goal": current_goal,
                "history": history,
            }

        judge_result = _assess_completion(
            goal=original_goal,
            execution_result=execute_result,
            model_name=judge_model,
        )

        iteration_record["judge_result"] = judge_result

        if not judge_result.get("success"):
            return {
                "success": False,
                "mode": "agent",
                "error": "judge failed",
                "iteration": iteration,
                "current_goal": current_goal,
                "history": history,
            }

        if judge_result.get("done"):
            return {
                "success": True,
                "mode": "agent",
                "goal": original_goal,
                "completed": True,
                "iterations_used": iteration,
                "final_reason": judge_result.get("reason", ""),
                "history": history,
            }

        next_goal = judge_result.get("next_goal", "").strip()
        if next_goal:
            current_goal = next_goal
        else:
            current_goal = f"{original_goal}\n\nContinue from previous execution result and finish the remaining work."

    return {
        "success": True,
        "mode": "agent",
        "goal": original_goal,
        "completed": False,
        "iterations_used": max_iterations,
        "final_reason": "max iterations reached",
        "history": history,
    }