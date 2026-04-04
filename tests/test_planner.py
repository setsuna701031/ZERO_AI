from core.planning.planner import Planner
from core.tools.tool_registry import ToolRegistry

def main():
    tool_registry = ToolRegistry(workspace_dir="workspace")

    planner = Planner(
        tool_registry=tool_registry,
        workspace_dir="workspace",
        debug=True,
    )

    user_input = "建立 hello.py 內容是 print('hello planner'), 然後執行 python hello.py"

    plan = planner.plan(user_input=user_input)

    print("\nPLAN RESULT")
    print(plan)

    print("\nSTEPS")
    for step in plan["steps"]:
        print(step)


if __name__ == "__main__":
    main()