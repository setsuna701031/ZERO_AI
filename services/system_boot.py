from __future__ import annotations

import copy
import importlib
import json
import os
import traceback
from typing import Any, Dict, List, Optional, Type

from core.planning.task_replanner import TaskReplanner
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.tasks.scheduler import Scheduler
from core.tasks.task_paths import TaskPathManager
from core.tasks.task_repository import TaskRepository


def _import_first_class(candidates: List[tuple[str, str]]) -> Optional[Type[Any]]:
    for module_path, class_name in candidates:
        try:
            module = importlib.import_module(module_path)
            value = getattr(module, class_name, None)
            if value is not None:
                return value
        except Exception:
            continue
    return None


def _resolve_planner_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.planning.planner", "Planner"),
            ("core.planner", "Planner"),
            ("planner", "Planner"),
        ]
    )


def _resolve_llm_client_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.system.llm_client", "LocalLLMClient"),
            ("core.llm_client", "LocalLLMClient"),
            ("llm_client", "LocalLLMClient"),
        ]
    )


def _resolve_llm_planner_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.system.llm_planner", "LLMPlanner"),
            ("core.planning.llm_planner", "LLMPlanner"),
            ("llm_planner", "LLMPlanner"),
        ]
    )


def _resolve_agent_loop_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.agent.agent_loop", "AgentLoop"),
            ("core.runtime.agent_loop", "AgentLoop"),
            ("agent_loop", "AgentLoop"),
        ]
    )


def _resolve_router_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.system.router", "SimpleRouter"),
            ("core.system.router", "Router"),
            ("core.router", "SimpleRouter"),
            ("core.router", "Router"),
            ("router", "SimpleRouter"),
            ("router", "Router"),
        ]
    )


def _resolve_verifier_class() -> Optional[Type[Any]]:
    return _import_first_class(
        [
            ("core.runtime.verifier", "Verifier"),
            ("core.verifier", "Verifier"),
            ("verifier", "Verifier"),
        ]
    )


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _build_llm_boot_config() -> Dict[str, Any]:
    plugin_name = os.environ.get("ZERO_LLM_PLUGIN", "").strip() or None

    model = (
        os.environ.get("ZERO_MODEL", "").strip()
        or os.environ.get("ZERO_LLM_MODEL", "").strip()
        or None
    )

    coder_model = (
        os.environ.get("ZERO_CODER_MODEL", "").strip()
        or os.environ.get("ZERO_LLM_CODER_MODEL", "").strip()
        or None
    )

    base_url = (
        os.environ.get("ZERO_LLM_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or None
    )

    timeout = _read_int_env("ZERO_LLM_TIMEOUT", 120)

    return {
        "plugin_name": plugin_name,
        "model": model,
        "coder_model": coder_model,
        "base_url": base_url,
        "timeout": timeout,
    }


class ZeroSystem:
    def __init__(self, workspace: str = "workspace") -> None:
        self.workspace = os.path.abspath(workspace)
        self.boot_errors: Dict[str, Dict[str, Any]] = {}

        self.path_manager = TaskPathManager(workspace_root=self.workspace)
        self.path_manager.ensure_workspace()

        workspace_paths = self.path_manager.get_workspace_paths()

        self.tasks_db_path = workspace_paths["tasks_index_file"]
        self.runtime_dir = workspace_paths["runtime_root"]
        self.logs_dir = workspace_paths["logs_root"]
        self.tasks_dir = workspace_paths["tasks_root"]
        self.scheduler_state_file = workspace_paths["scheduler_state_file"]
        self.memory_root = workspace_paths["memory_root"]
        self.knowledge_root = workspace_paths["knowledge_root"]
        self.cache_root = workspace_paths["cache_root"]

        if not os.path.exists(self.tasks_db_path):
            with open(self.tasks_db_path, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)

        self.memory_store = None
        self.runtime_store = None
        self.verifier = None
        self.safety_guard = None

        self.router = None
        self.planner = None
        self.llm_client = None
        self.llm_planner = None
        self.agent_loop = None

        # 預設關閉 llm planner，避免 deterministic planner 被搶走
        self.enable_llm_planner = _read_bool_env("ZERO_ENABLE_LLM_PLANNER", False)

        self.task_repository = TaskRepository(self.tasks_db_path)

        self.task_runtime = TaskRuntime(
            workspace_root=self.workspace,
            debug=False,
        )

        router_cls = _resolve_router_class()
        if router_cls is not None:
            try:
                self.router = router_cls()
            except TypeError:
                try:
                    self.router = router_cls(workspace_root=self.workspace)
                except Exception:
                    self.router = None
            except Exception:
                self.router = None

        llm_client_cls = _resolve_llm_client_class()
        if llm_client_cls is not None:
            llm_boot = _build_llm_boot_config()

            try:
                self.llm_client = llm_client_cls(
                    plugin_name=llm_boot["plugin_name"],
                    base_url=llm_boot["base_url"],
                    model=llm_boot["model"],
                    coder_model=llm_boot["coder_model"],
                    timeout=llm_boot["timeout"],
                )
            except TypeError:
                try:
                    self.llm_client = llm_client_cls(
                        base_url=llm_boot["base_url"],
                        model=llm_boot["model"],
                        coder_model=llm_boot["coder_model"],
                        timeout=llm_boot["timeout"],
                    )
                except TypeError:
                    try:
                        self.llm_client = llm_client_cls()
                    except Exception:
                        self.llm_client = None
                except Exception:
                    self.llm_client = None
            except Exception:
                self.llm_client = None

        verifier_cls = _resolve_verifier_class()
        if verifier_cls is not None:
            try:
                self.verifier = verifier_cls(
                    llm_client=self.llm_client,
                    debug=False,
                )
            except TypeError:
                try:
                    self.verifier = verifier_cls(self.llm_client)
                except Exception:
                    self.verifier = None
            except Exception:
                self.verifier = None

        self.step_executor = StepExecutor(
            workspace_root=self.workspace,
            llm_client=self.llm_client,
            debug=False,
        )

        planner_cls = _resolve_planner_class()
        if planner_cls is not None:
            try:
                self.planner = planner_cls(
                    memory_store=self.memory_store,
                    runtime_store=self.runtime_store,
                    step_executor=self.step_executor,
                    tool_registry=getattr(self.step_executor, "tool_registry", None),
                    workspace_root=self.workspace,
                    debug=False,
                )
            except TypeError:
                try:
                    self.planner = planner_cls(
                        workspace_root=self.workspace,
                        debug=False,
                    )
                except Exception:
                    self.planner = None
            except Exception:
                self.planner = None

        # llm_planner 改成可選，不再預設啟用
        if self.enable_llm_planner:
            llm_planner_cls = _resolve_llm_planner_class()
            if llm_planner_cls is not None and self.llm_client is not None:
                try:
                    self.llm_planner = llm_planner_cls(
                        llm_client=self.llm_client,
                        debug=False,
                    )
                except TypeError:
                    try:
                        self.llm_planner = llm_planner_cls(
                            llm_client=self.llm_client,
                        )
                    except Exception:
                        self.llm_planner = None
                except Exception:
                    self.llm_planner = None
        else:
            self.llm_planner = None

        self.replanner = TaskReplanner(
            workspace_dir=self.workspace,
            planner=self.planner,
        )

        self.task_runner = TaskRunner(
            step_executor=self.step_executor,
            replanner=self.replanner,
            task_runtime=self.task_runtime,
            debug=False,
        )

        self.scheduler = Scheduler(
            task_repo=self.task_repository,
            workspace_dir=self.workspace,
            task_runtime=self.task_runtime,
            task_runner=self.task_runner,
            step_executor=self.step_executor,
            debug=False,
        )

        self.task_workspace = getattr(self.scheduler, "task_workspace", None)

        agent_loop_cls = _resolve_agent_loop_class()
        if agent_loop_cls is not None:
            self.agent_loop = self._build_agent_loop(agent_loop_cls)

        try:
            setattr(self.scheduler, "agent_loop", self.agent_loop)
        except Exception:
            pass

        try:
            setattr(self.task_runner, "agent_loop", self.agent_loop)
        except Exception:
            pass

        try:
            setattr(self, "loop", self.agent_loop)
        except Exception:
            pass

        self.tick_count = 0

    def _record_boot_error(self, component: str, stage: str, error: Exception) -> None:
        self.boot_errors[component] = {
            "stage": stage,
            "error": f"{error.__class__.__name__}: {error}",
            "traceback": traceback.format_exc(),
        }

    def _build_agent_loop(self, agent_loop_cls: Type[Any]) -> Any:
        first_error: Optional[Exception] = None

        try:
            return agent_loop_cls(
                router=self.router,
                planner=self.planner,
                llm_planner=self.llm_planner,
                step_executor=self.step_executor,
                verifier=self.verifier,
                safety_guard=self.safety_guard,
                memory_store=self.memory_store,
                runtime_store=self.runtime_store,
                scheduler=self.scheduler,
                task_manager=self.scheduler,
                task_workspace=self.task_workspace,
                task_runtime=self.task_runtime,
                task_runner=self.task_runner,
                replanner=self.replanner,
                llm_client=self.llm_client,
                debug=False,
            )
        except TypeError as e:
            first_error = e
            self._record_boot_error("agent_loop_primary", "constructor", e)
        except Exception as e:
            self._record_boot_error("agent_loop_primary", "constructor", e)
            return None

        try:
            return agent_loop_cls(
                router=self.router,
                planner=self.planner,
                step_executor=self.step_executor,
                verifier=self.verifier,
                safety_guard=self.safety_guard,
                memory_store=self.memory_store,
                runtime_store=self.runtime_store,
                scheduler=self.scheduler,
                task_manager=self.scheduler,
                task_workspace=self.task_workspace,
                task_runtime=self.task_runtime,
                task_runner=self.task_runner,
                replanner=self.replanner,
                llm_client=self.llm_client,
                debug=False,
            )
        except Exception as e:
            self._record_boot_error("agent_loop_fallback", "constructor", e)
            if first_error is not None:
                print("[boot_system] agent_loop primary constructor failed:")
                print(self.boot_errors["agent_loop_primary"]["error"])
            print("[boot_system] agent_loop fallback constructor failed:")
            print(f"{e.__class__.__name__}: {e}")
            return None

    def tick(self) -> Dict[str, Any]:
        self.tick_count += 1
        sched_result = self.scheduler.tick(current_tick=self.tick_count)

        if not isinstance(sched_result, dict):
            return {
                "ok": False,
                "status": "failed",
                "message": "scheduler returned invalid result",
                "tick": self.tick_count,
                "raw_result": sched_result,
            }

        action = str(sched_result.get("action", "") or "").strip().lower()
        status = str(sched_result.get("status", "") or "").strip().lower()

        if action == "scheduler_idle":
            return {
                "ok": True,
                "status": "idle",
                "message": sched_result.get("message", "no task scheduled"),
                "tick": self.tick_count,
                "ready_queue": copy.deepcopy(sched_result.get("ready_queue", [])),
            }

        return {
            "ok": bool(sched_result.get("ok", False)),
            "task_name": sched_result.get("task_name"),
            "task_id": sched_result.get("task_id"),
            "status": status,
            "action": sched_result.get("action"),
            "message": sched_result.get("message", ""),
            "error": sched_result.get("error"),
            "tick": self.tick_count,
            "final_answer": sched_result.get("final_answer", ""),
            "current_step_index": sched_result.get("current_step_index"),
            "step_count": sched_result.get("step_count"),
            "raw_result": copy.deepcopy(sched_result),
        }

    def run_until_idle(self, max_ticks: int = 50) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for _ in range(max_ticks):
            r = self.tick()
            results.append(copy.deepcopy(r))

            if str(r.get("status", "") or "").strip().lower() == "idle":
                break

        return results

    def health(self) -> Dict[str, Any]:
        scheduler_status = self.scheduler.status() if hasattr(self.scheduler, "status") else {}

        return {
            "ok": True,
            "system": "ZERO",
            "workspace": self.workspace,
            "tasks_db_path": self.tasks_db_path,
            "tasks_dir": self.tasks_dir,
            "runtime_dir": self.runtime_dir,
            "logs_dir": self.logs_dir,
            "scheduler_state_file": self.scheduler_state_file,
            "memory_root": self.memory_root,
            "knowledge_root": self.knowledge_root,
            "cache_root": self.cache_root,
            "router_type": type(self.router).__name__ if self.router is not None else None,
            "step_executor_type": type(self.step_executor).__name__,
            "planner_type": type(self.planner).__name__ if self.planner is not None else None,
            "llm_client_type": type(self.llm_client).__name__ if self.llm_client is not None else None,
            "llm_planner_type": type(self.llm_planner).__name__ if self.llm_planner is not None else None,
            "llm_planner_enabled": self.enable_llm_planner,
            "agent_loop_type": type(self.agent_loop).__name__ if self.agent_loop is not None else None,
            "verifier_type": type(self.verifier).__name__ if self.verifier is not None else None,
            "replanner_type": type(self.replanner).__name__,
            "task_runner_type": type(self.task_runner).__name__,
            "scheduler_type": type(self.scheduler).__name__,
            "task_repository_type": type(self.task_repository).__name__,
            "task_runtime_type": type(self.task_runtime).__name__,
            "tick_count": self.tick_count,
            "scheduler_status": copy.deepcopy(scheduler_status),
            "boot_errors": copy.deepcopy(self.boot_errors),
        }

    def get_queue_rows(self) -> Any:
        fn = getattr(self.scheduler, "get_queue_rows", None)
        if callable(fn):
            return fn()
        return {
            "ok": False,
            "error": "scheduler.get_queue_rows not available",
        }

    def get_queue_snapshot(self) -> Any:
        fn = getattr(self.scheduler, "get_queue_snapshot", None)
        if callable(fn):
            return fn()
        if hasattr(self.scheduler, "list_queue"):
            return {
                "ok": True,
                "queue": self.scheduler.list_queue(),
            }
        return {
            "ok": False,
            "error": "scheduler.get_queue_snapshot not available",
        }

    def create_task(self, **kwargs: Any) -> Dict[str, Any]:
        fn = getattr(self.scheduler, "create_task", None)
        if not callable(fn):
            return {
                "ok": False,
                "error": "scheduler.create_task not available",
            }

        try:
            result = fn(**kwargs)
            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "error": "scheduler.create_task returned invalid result",
                    "raw_result": result,
                }
            return result
        except Exception as e:
            return {
                "ok": False,
                "error": f"create_task exception: {e}",
            }

    def submit_task(self, task_id: str) -> Any:
        fn = getattr(self.scheduler, "submit_existing_task", None)
        if callable(fn):
            try:
                return fn(task_id)
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"submit_task exception: {e}",
                    "task_id": task_id,
                }

        return {
            "ok": False,
            "error": "scheduler.submit_existing_task not available",
            "task_id": task_id,
        }

    def get_task(self, task_name: str) -> Dict[str, Any]:
        helper = getattr(self.scheduler, "_get_task_from_repo", None)
        if callable(helper):
            try:
                task = helper(task_name)
                if isinstance(task, dict):
                    return {
                        "ok": True,
                        "task": copy.deepcopy(task),
                    }
            except Exception:
                pass

        task = self.task_repository.get_task(task_name)
        if task is None:
            return {
                "ok": False,
                "error": "task not found",
                "task_name": task_name,
            }
        return {
            "ok": True,
            "task": copy.deepcopy(task),
        }

    def list_tasks(self) -> Dict[str, Any]:
        helper = getattr(self.scheduler, "_list_repo_tasks", None)
        if callable(helper):
            try:
                tasks = helper()
                if isinstance(tasks, list):
                    return {
                        "ok": True,
                        "tasks": copy.deepcopy(tasks),
                        "count": len(tasks),
                    }
            except Exception:
                pass

        tasks = self.task_repository.list_tasks()
        if not isinstance(tasks, list):
            tasks = []
        return {
            "ok": True,
            "tasks": copy.deepcopy(tasks),
            "count": len(tasks),
        }

    def pause_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "pause_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.pause_task not available",
            "task_name": task_name,
        }

    def resume_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "resume_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.resume_task not available",
            "task_name": task_name,
        }

    def cancel_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "cancel_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.cancel_task not available",
            "task_name": task_name,
        }

    def set_task_priority(self, task_name: str, priority: int) -> Any:
        fn = getattr(self.scheduler, "set_task_priority", None)
        if callable(fn):
            return fn(task_name, priority)
        return {
            "ok": False,
            "error": "scheduler.set_task_priority not available",
            "task_name": task_name,
            "priority": priority,
        }

    def scheduler_boot(self) -> Dict[str, Any]:
        if hasattr(self.scheduler, "boot"):
            return self.scheduler.boot()
        return {
            "ok": False,
            "error": "scheduler.boot not available",
        }

    def scheduler_status(self) -> Dict[str, Any]:
        if hasattr(self.scheduler, "status"):
            return self.scheduler.status()
        return {
            "ok": False,
            "error": "scheduler.status not available",
        }


def boot_system(workspace_dir: str = "workspace") -> ZeroSystem:
    return ZeroSystem(workspace=workspace_dir)