from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "core" / "tasks" / "scheduler_core" / "simple_step_executor_helpers.py"
HANDLERS = ROOT / "core" / "tasks" / "scheduler_core" / "simple_step_basic_handlers.py"


APPEND_HANDLER = r'''

def handle_simple_append_file_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
    legacy_template_detected,
    contract_failure,
    resolve_previous_result_text_for_contract,
    render_simple_step_template,
    step_contract_metadata,
) -> Dict[str, Any]:
    raw_path = str(step.get("path") or "").strip()
    if not raw_path:
        raise ValueError("append_file step missing path")

    if legacy_template_detected(step):
        return contract_failure(
            step=step,
            error_type="legacy_contract_detected",
            message="legacy previous_result template is not supported by simple runtime",
        )

    if bool(step.get("use_previous_text", False)):
        ok, content, failure = resolve_previous_result_text_for_contract(scheduler, task, step)
        if not ok:
            return failure
    else:
        content = step.get("content", "")

    if content is None:
        content = ""
    content = render_simple_step_template(content, scheduler=scheduler, task=task)

    if bool(step.get("ensure_trailing_newline", False)) and content and not content.endswith("\n"):
        content += "\n"

    if str(step_scope or "").strip().lower() == "shared":
        full_path = scheduler._resolve_step_path(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope="shared",
        )
    else:
        full_path = scheduler._resolve_guard_target_path(
            raw_path=raw_path,
            task_dir=task_dir,
            scope=step_scope,
            resolved_path=str(guard_result.get("resolved_path") or ""),
        )

    if os.path.exists(full_path) and os.path.isdir(full_path):
        raise IsADirectoryError(f"append_file target is a directory: {full_path}")

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    before_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0

    with open(full_path, "a", encoding="utf-8", newline="") as f:
        f.write(content)

    after_size = os.path.getsize(full_path) if os.path.exists(full_path) else before_size

    return {
        "type": "append_file",
        "path": raw_path,
        "full_path": full_path,
        "scope": step_scope,
        "bytes_before": before_size,
        "bytes_after": after_size,
        "bytes_appended": max(0, after_size - before_size),
        "content": content,
        "chars_appended": len(content),
        "created": before_size == 0,
        "ensure_trailing_newline": bool(step.get("ensure_trailing_newline", False)),
        **step_contract_metadata(step),
    }
'''


def main() -> None:
    handlers_text = HANDLERS.read_text(encoding="utf-8")
    if "def handle_simple_append_file_step(" not in handlers_text:
        handlers_text = handlers_text.rstrip() + APPEND_HANDLER + "\n"
        HANDLERS.write_text(handlers_text, encoding="utf-8")

    text = EXECUTOR.read_text(encoding="utf-8")

    old_import = (
        "from .simple_step_basic_handlers import "
        "handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_write_file_step\n"
    )
    new_import = (
        "from .simple_step_basic_handlers import "
        "handle_simple_append_file_step, handle_simple_ensure_file_step, "
        "handle_simple_noop_step, handle_simple_write_file_step\n"
    )
    if old_import in text:
        text = text.replace(old_import, new_import, 1)

    start = text.index('    if step_type == "append_file":')
    end = text.index('    if step_type == "read_file":', start)

    replacement = '''    if step_type == "append_file":
        return handle_simple_append_file_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
            guard_result=guard_result,
            legacy_template_detected=_legacy_template_detected,
            contract_failure=_contract_failure,
            resolve_previous_result_text_for_contract=_resolve_previous_result_text_for_contract,
            render_simple_step_template=_render_simple_step_template,
            step_contract_metadata=_step_contract_metadata,
        )

'''

    text = text[:start] + replacement + text[end:]
    EXECUTOR.write_text(text, encoding="utf-8")

    print(f"updated: {EXECUTOR}")
    print(f"updated: {HANDLERS}")


if __name__ == "__main__":
    main()