from pathlib import Path

handlers = Path("core/tasks/scheduler_core/simple_step_basic_handlers.py")
executor = Path("core/tasks/scheduler_core/simple_step_executor_helpers.py")

handler_text = handlers.read_text(encoding="utf-8")
executor_text = executor.read_text(encoding="utf-8")

if "import json" not in handler_text:
    handler_text = handler_text.replace("import os\n", "import json\nimport os\n", 1)

new_func = r'''
def handle_simple_verify_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
) -> Dict[str, Any]:
    contains = step.get("contains", None)
    equals = step.get("equals", None)
    exists = step.get("exists", None)
    path = str(step.get("path") or "").strip()

    if contains is None and equals is None and exists is None and not path:
        raise ValueError("verify step requires path / contains / equals / exists")

    target_text = ""
    full_path = ""

    if path:
        full_path = scheduler._resolve_read_path_with_fallback(
            raw_path=path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope=step_scope,
        )

        read_guard = scheduler.execution_guard.check_step(
            step={"type": "read_file", "path": full_path},
            task_dir=task_dir,
        )
        if not bool(read_guard.get("ok")):
            raise PermissionError(str(read_guard.get("error") or "guard blocked verify read"))

        file_exists = os.path.exists(full_path)

        if exists is True and not file_exists:
            raise FileNotFoundError(f"verify file not found: {full_path}")

        if exists is False and file_exists:
            raise RuntimeError(f"verify failed: file should not exist: {full_path}")

        if (contains is not None or equals is not None or exists is not False) and not file_exists:
            raise FileNotFoundError(f"verify file not found: {full_path}")

        if file_exists and (contains is not None or equals is not None):
            with open(full_path, "r", encoding="utf-8") as f:
                target_text = f.read()
    else:
        last = task.get("last_step_result")
        if isinstance(last, dict):
            last_result = last.get("result")
            if isinstance(last_result, dict):
                if "stdout" in last_result:
                    target_text = str(last_result.get("stdout") or "")
                elif "content" in last_result:
                    target_text = str(last_result.get("content") or "")
                else:
                    target_text = json.dumps(last_result, ensure_ascii=False)
            else:
                target_text = str(last_result or "")

    if contains is not None:
        contains_text = str(contains)
        if contains_text not in target_text:
            raise RuntimeError(f"verify contains failed: '{contains_text}' not found")

    if equals is not None:
        expected = str(equals)
        if str(target_text).strip() != expected.strip():
            raise RuntimeError(
                f"verify equals failed: expected exact match '{expected}', got '{str(target_text).strip()}'"
            )

    return {
        "type": "verify",
        "ok": True,
        "path": path,
        "full_path": full_path,
        "scope": step_scope,
        "contains": contains,
        "equals": equals,
        "exists": exists,
        "checked_text": target_text,
        "verified": True,
    }
'''

if "def handle_simple_verify_step(" not in handler_text:
    handler_text = handler_text.rstrip() + "\n\n" + new_func.lstrip() + "\n"
    handlers.write_text(handler_text, encoding="utf-8")
    print(f"updated: {handlers}")
else:
    print(f"already has handler: {handlers}")

old_import = "from .simple_step_basic_handlers import handle_simple_append_file_step, handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_read_file_step, handle_simple_write_file_step"
new_import = "from .simple_step_basic_handlers import handle_simple_append_file_step, handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_read_file_step, handle_simple_verify_step, handle_simple_write_file_step"

if old_import in executor_text:
    executor_text = executor_text.replace(old_import, new_import, 1)

start = executor_text.index('    if step_type == "verify":')
end = executor_text.index("\n    return None", start)

new_block = r'''    if step_type == "verify":
        return handle_simple_verify_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
        )
'''

executor_text = executor_text[:start] + new_block + executor_text[end:]
executor.write_text(executor_text, encoding="utf-8")
print(f"updated: {executor}")
