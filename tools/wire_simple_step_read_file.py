from pathlib import Path

handlers = Path("core/tasks/scheduler_core/simple_step_basic_handlers.py")
executor = Path("core/tasks/scheduler_core/simple_step_executor_helpers.py")

handler_text = handlers.read_text(encoding="utf-8")
executor_text = executor.read_text(encoding="utf-8")

new_func = r'''
def handle_simple_read_file_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
) -> Dict[str, Any]:
    raw_path = str(step.get("path") or "").strip()
    if not raw_path:
        raise ValueError("read_file step missing path")

    full_path = scheduler._resolve_read_path_with_fallback(
        raw_path=raw_path,
        task_dir=task_dir,
        shared_dir=scheduler.shared_dir,
        scope=step_scope,
    )

    guard_check = scheduler.execution_guard.check_step(
        step={"type": "read_file", "path": full_path},
        task_dir=task_dir,
    )
    if not bool(guard_check.get("ok")):
        raise PermissionError(str(guard_check.get("error") or "guard blocked read"))

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"file not found: {full_path}")

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "type": "read_file",
        "path": raw_path,
        "full_path": full_path,
        "scope": step_scope,
        "content": content,
    }
'''

if "def handle_simple_read_file_step(" not in handler_text:
    handler_text = handler_text.rstrip() + "\n\n" + new_func.lstrip() + "\n"
    handlers.write_text(handler_text, encoding="utf-8")
    print(f"updated: {handlers}")
else:
    print(f"already has handler: {handlers}")

old_import = "from .simple_step_basic_handlers import handle_simple_append_file_step, handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_write_file_step"
new_import = "from .simple_step_basic_handlers import handle_simple_append_file_step, handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_read_file_step, handle_simple_write_file_step"

if old_import in executor_text:
    executor_text = executor_text.replace(old_import, new_import, 1)
elif "handle_simple_read_file_step" not in executor_text:
    raise RuntimeError("import line not found")

old_block = r'''    if step_type == "read_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("read_file step missing path")

        full_path = scheduler._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope=step_scope,
        )

        guard_check = scheduler.execution_guard.check_step(
            step={"type": "read_file", "path": full_path},
            task_dir=task_dir,
        )
        if not bool(guard_check.get("ok")):
            raise PermissionError(str(guard_check.get("error") or "guard blocked read"))

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "type": "read_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "content": content,
        }
'''

new_block = r'''    if step_type == "read_file":
        return handle_simple_read_file_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
        )
'''

if old_block in executor_text:
    executor_text = executor_text.replace(old_block, new_block, 1)
    executor.write_text(executor_text, encoding="utf-8")
    print(f"updated: {executor}")
elif new_block in executor_text:
    print(f"already wired: {executor}")
else:
    raise RuntimeError("read_file block not found")
