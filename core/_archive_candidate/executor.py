from core.tool_router import run_tool, get_available_tools
from core.llm_client import ask_local_llm
from core.model_router import select_model


def execute_plan(plan: dict) -> dict:

    steps = plan.get("steps", [])
    results = []

    if not steps:
        return {
            "success": False,
            "error": "plan has no steps"
        }

    for step in steps:

        step_id = step.get("step")
        task = step.get("task", "")

        # 判斷模型
        model_info = select_model(task)

        llm_result = ask_local_llm(
            task,
            model_name=model_info["model"]
        )

        results.append({
            "step": step_id,
            "task": task,
            "model": model_info["model"],
            "result": llm_result.get("answer", ""),
            "success": llm_result.get("success", False)
        })

    return {
        "success": True,
        "steps_executed": results
    }