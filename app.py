from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.agent_loop import AgentLoop
from core.experience_planner import ExperiencePlanner
from core.memory_manager import MemoryManager
from core.step_executor import DummyStepExecutor
from core.task_manager import TaskManager
from core.task_runtime import TaskRuntime
from core.tool_registry import ToolRegistry


DIVIDER = "=" * 48


class TaskStepExecutorAdapter:
    """
    把 AgentLoop 需要的 execute_task(task, context)
    轉接到目前的 DummyStepExecutor.execute(step, workspace)

    目前策略：
    - 依 task title 映射成 workspace step
    - 成功就回傳 message
    - 失敗就 raise，讓 AgentLoop 標記 task failed / retry
    """

    def __init__(
        self,
        step_executor: DummyStepExecutor,
        tool_registry: ToolRegistry,
        workspace: str = "workspace",
    ) -> None:
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace = workspace

    def execute_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        step = self._task_to_step(task, context=context)
        result = self.step_executor.execute(step, workspace=self.workspace)

        if not result.get("ok"):
            raise RuntimeError(result.get("message", "step execution failed"))

        return str(result.get("message") or "step completed")

    # ------------------------------------------------------------------
    # task -> step mapping
    # ------------------------------------------------------------------
    def _task_to_step(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        title = str(task.get("title", "")).strip()
        task_id = str(task.get("id", "")).strip()
        step_index = int(task.get("meta", {}).get("step_index", 0) or 0)

        action_input = self._infer_workspace_action(
            title=title,
            task=task,
            context=context,
        )

        return {
            "id": task_id,
            "title": title,
            "index": step_index,
            "tool": "workspace",
            "input": action_input,
        }

    def _infer_workspace_action(
        self,
        title: str,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        目前先做簡單規則式映射。

        常見 subtasks：
        - 分析需求
        - 規劃執行步驟
        - 實作主要內容
        - 驗證結果

        注意：
        fail_first / always_fail 必須放前面，
        否則 title 同時包含「分析 / 規劃 / 實作 / 驗證」時，會先被一般規則吃掉，
        retry 測試就永遠不會真正觸發。
        """

        lower_title = title.lower()

        # --------------------------------------------------------------
        # 先處理 retry / fail 測試關鍵字
        # --------------------------------------------------------------
        if "fail_first" in lower_title:
            return {
                "action": "mkdir",
                "path": "demo_fail_first",
            }

        if "always_fail" in lower_title:
            return {
                "action": "mkdir",
                "path": "demo_always_fail",
            }

        # --------------------------------------------------------------
        # 一般流程映射
        # --------------------------------------------------------------
        if ("分析" in title) or ("需求" in title):
            return {
                "action": "append_text",
                "path": "plan.txt",
                "content": f"[分析] {title}\n",
            }

        if ("規劃" in title) or ("步驟" in title) or ("計畫" in title):
            return {
                "action": "append_text",
                "path": "plan.txt",
                "content": f"[規劃] {title}\n",
            }

        if ("實作" in title) or ("建立" in title) or ("生成" in title) or ("撰寫" in title):
            return {
                "action": "mkdir",
                "path": "demo_ok",
            }

        if ("驗證" in title) or ("測試" in title) or ("確認" in title) or ("檢查" in title):
            return {
                "action": "exists",
                "path": "demo_ok",
            }

        return {
            "action": "mkdir",
            "path": "demo_ok",
        }


def print_help() -> None:
    print("Available commands:")
    print("  task new <goal>        建立新 root task 並拆 subtasks")
    print("  task tree              顯示目前 active task tree")
    print("  task roots             顯示所有 root tasks")
    print("  task next              執行下一個 leaf task")
    print("  task run               持續執行直到完成或失敗")
    print("  task reset             清除目前 runtime active task")
    print("  runtime show           顯示 runtime 狀態")
    print("  runtime events         顯示 runtime events")
    print("  memory recent          顯示最近 memory records")
    print("  memory task            顯示目前 active root task 的 memories")
    print("  memory search <text>   搜尋 memory")
    print("  memory plan <goal>     顯示 planner 看到的經驗上下文")
    print("  memory clear           清空 memory store")
    print("  tools show             顯示 tool registry 狀態")
    print("  help")
    print("  exit")


def parse_value(command: str, prefix: str) -> Optional[str]:
    if not command.startswith(prefix):
        return None
    value = command[len(prefix):].strip()
    if not value:
        return None
    return value


def print_root_tasks(task_manager: TaskManager) -> None:
    roots = task_manager.list_root_tasks()
    if not roots:
        print("No root tasks.")
        return

    print(DIVIDER)
    for root in roots:
        print(
            f"{root['id']} | status={root['status']} | "
            f"title={root['title']} | children={len(root.get('children', []))}"
        )
    print(DIVIDER)


def print_tree_node(node: Dict[str, Any], indent: int = 0) -> None:
    prefix = "  " * indent
    task_id = node.get("id", "")
    title = node.get("title", "")
    status = node.get("status", "")
    result = node.get("result")
    error = node.get("error")

    print(f"{prefix}- {task_id} | {status} | {title}")

    if result:
        print(f"{prefix}  result: {result}")
    if error:
        print(f"{prefix}  error: {error}")

    children = node.get("children_nodes", []) or []
    for child in children:
        print_tree_node(child, indent + 1)


def print_active_tree(agent: AgentLoop) -> None:
    tree = agent.get_active_tree()
    if tree is None:
        print("No active task tree.")
        return

    print(DIVIDER)
    print_tree_node(tree)
    print(DIVIDER)


def print_runtime(runtime: TaskRuntime) -> None:
    print(DIVIDER)
    print(f"Active Root Task: {runtime.get_active_root_task()}")
    print(f"Current Task: {runtime.get_current_task()}")
    print(f"Last Result: {runtime.get_last_result()}")
    print(f"Last Error: {runtime.get_last_error()}")
    print(f"Recorded Results: {len(runtime.step_results)}")
    print(f"Recorded Errors: {len(runtime.step_errors)}")
    print(f"Events: {len(runtime.events)}")
    print(DIVIDER)


def print_runtime_events(runtime: TaskRuntime) -> None:
    events = runtime.get_events()
    if not events:
        print("No runtime events.")
        return

    print(DIVIDER)
    for item in events:
        print(
            f"{item['timestamp']} | {item['event_type']} | "
            f"task={item['task_id']} | {item['message']}"
        )
        meta = item.get("meta", {})
        if meta:
            print(f"  meta={meta}")
    print(DIVIDER)


def print_memory_records(records: List[Dict[str, Any]]) -> None:
    if not records:
        print("No memory records.")
        return

    print(DIVIDER)
    for item in records:
        print(
            f"{item.get('created_at')} | {item.get('memory_type')} | "
            f"root={item.get('root_task_id')} | task={item.get('task_id')}"
        )
        content = item.get("content", {})
        print(f"  content={content}")
    print(DIVIDER)


def print_planning_context(context: Dict[str, Any]) -> None:
    print(DIVIDER)
    print(f"Goal: {context.get('goal')}")
    print(f"Source Count: {context.get('source_count')}")

    similar_goals = context.get("similar_goals", []) or []
    successful_steps = context.get("successful_steps", []) or []
    lessons = context.get("lessons", []) or []
    failed_notes = context.get("failed_notes", []) or []

    print("Similar Goals:")
    if similar_goals:
        for item in similar_goals:
            print(f"  - {item}")
    else:
        print("  (none)")

    print("Successful Steps:")
    if successful_steps:
        for item in successful_steps:
            print(f"  - {item}")
    else:
        print("  (none)")

    print("Lessons:")
    if lessons:
        for item in lessons:
            print(f"  - {item}")
    else:
        print("  (none)")

    print("Failed Notes:")
    if failed_notes:
        for item in failed_notes:
            print(f"  - {item}")
    else:
        print("  (none)")

    print(DIVIDER)


def print_tools_info(tool_registry: ToolRegistry) -> None:
    info = tool_registry.debug_info()
    print(DIVIDER)
    print(f"workspace_root: {info.get('workspace_root')}")
    print(f"project_root: {info.get('project_root')}")
    print(f"tools: {info.get('tools')}")
    print(DIVIDER)


def main() -> None:
    task_manager = TaskManager()
    task_runtime = TaskRuntime()
    memory_manager = MemoryManager(storage_path="data/memory_store.json")
    planner = ExperiencePlanner(memory_manager=memory_manager)

    tool_registry = ToolRegistry(
        workspace_root="workspace",
        project_root=".",
    )

    step_executor = DummyStepExecutor()

    executor = TaskStepExecutorAdapter(
        step_executor=step_executor,
        tool_registry=tool_registry,
        workspace="workspace",
    )

    agent = AgentLoop(
        task_manager=task_manager,
        task_runtime=task_runtime,
        planner=planner,
        executor=executor,
        memory_manager=memory_manager,
    )

    print("ZERO>")
    print_help()
    print(DIVIDER)

    while True:
        try:
            command = input("ZERO> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print("Bye.")
            break

        if not command:
            continue

        if command in {"exit", "quit"}:
            print("Bye.")
            break

        if command == "help":
            print_help()
            continue

        if command == "task roots":
            print_root_tasks(task_manager)
            continue

        if command == "task tree":
            print_active_tree(agent)
            continue

        if command == "runtime show":
            print_runtime(task_runtime)
            continue

        if command == "runtime events":
            print_runtime_events(task_runtime)
            continue

        if command == "task reset":
            agent.reset_active_task()
            print("Active runtime reset.")
            continue

        if command == "memory recent":
            records = memory_manager.get_recent_records(limit=20)
            print_memory_records(records)
            continue

        if command == "memory task":
            root_task_id = task_runtime.get_active_root_task()
            if not root_task_id:
                print("No active root task.")
                continue
            records = memory_manager.get_records_by_root_task(root_task_id)
            print_memory_records(records)
            continue

        if command == "memory clear":
            memory_manager.clear()
            print("Memory cleared.")
            continue

        if command == "tools show":
            print_tools_info(tool_registry)
            continue

        keyword = parse_value(command, "memory search ")
        if keyword is not None:
            records = memory_manager.search_text(keyword, limit=20)
            print_memory_records(records)
            continue

        preview_goal = parse_value(command, "memory plan ")
        if preview_goal is not None:
            context = planner.preview_context(preview_goal)
            print_planning_context(context)
            planned_steps = planner.plan(preview_goal)
            print("Planned Steps:")
            for idx, step in enumerate(planned_steps, start=1):
                print(f"  {idx}. {step}")
            print(DIVIDER)
            continue

        goal = parse_value(command, "task new ")
        if goal is not None:
            result = agent.start_new_task(goal)
            print(result.to_dict())
            print_active_tree(agent)
            continue

        if command == "task next":
            result = agent.run_next_step()
            print(result.to_dict())
            print_active_tree(agent)
            continue

        if command == "task run":
            result = agent.run_until_done()
            print(result.to_dict())
            print_active_tree(agent)
            continue

        print("Unknown command. Type 'help' for available commands.")


if __name__ == "__main__":
    main()