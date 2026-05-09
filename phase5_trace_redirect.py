from pathlib import Path

p = Path("core/tasks/scheduler.py")
s = p.read_text(encoding="utf-8")

replacements = {
'''    def _save_trace_for_task(self, task: Dict[str, Any], trace: ExecutionTrace) -> Optional[str]:
        return save_trace_for_task(scheduler=self, task=task, trace=trace)
''':
'''    def _save_trace_for_task(self, task: Dict[str, Any], trace: ExecutionTrace) -> Optional[str]:
        return self.trace_runtime.save_scheduler_trace_for_task(
            task=task,
            trace=trace,
            tasks_root=self.tasks_root,
            task_id=self._extract_task_id(task),
        )
''',

'''        return trace_summary(
            scheduler=self,
            trace=trace,
            task=task,
            summary=summary,
            tick=tick,
            extra=extra,
        )
''':
'''        return self.trace_runtime.scheduler_trace_summary(
            scheduler=self,
            trace=trace,
            task=task,
            summary=summary,
            tick=tick,
            extra=extra,
        )
''',

'''        return trace_status(
            scheduler=self,
            trace=trace,
            task=task,
            status=status,
            tick=tick,
            final_answer=final_answer,
            extra=extra,
        )
''':
'''        return self.trace_runtime.scheduler_trace_status(
            scheduler=self,
            trace=trace,
            task=task,
            status=status,
            tick=tick,
            final_answer=final_answer,
            extra=extra,
        )
''',

'''        return trace_step(
            scheduler=self,
            trace=trace,
            task=task,
            step_index=step_index,
            step=step,
            ok=ok,
            result=result,
            error=error,
            tick=tick,
        )
''':
'''        return self.trace_runtime.scheduler_trace_step(
            scheduler=self,
            trace=trace,
            task=task,
            step_index=step_index,
            step=step,
            ok=ok,
            result=result,
            error=error,
            tick=tick,
        )
''',

'''        return trace_replan(
            scheduler=self,
            trace=trace,
            task=task,
            tick=tick,
            replan_result=replan_result,
        )
''':
'''        return self.trace_runtime.scheduler_trace_replan(
            scheduler=self,
            trace=trace,
            task=task,
            tick=tick,
            replan_result=replan_result,
        )
''',
}

for old, new in replacements.items():
    if old not in s:
        raise SystemExit(f"missing block:\n{old}")
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
