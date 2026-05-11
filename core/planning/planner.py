from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from core.planning.planner_document_logic import (
    plan_document_flow,
    plan_structured_document_task,
)
from core.planning.planner_rule_parser import (
    extract_command,
    extract_file_path,
    extract_run_python_request,
    extract_verify_request,
    extract_write_request,
    has_verify_intent,
    infer_path_scope,
    looks_like_read,
    looks_like_search,
    resolve_read_path,
)
from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v35.3

    本版重點：
    1. 保留 document flow 偵測
    2. 保留 command / write / ensure / read / search 規則
    3. 保留 run_python 規則
    4. 保留 verify 規則
    5. verify 類句型先於 document flow 判定
    6. 保留結構化 document task 入口
    7. planner result contract 固定化
    8. step schema 正規化
    9. 保留 action layer
    10. semantic execution routing：
        - summary -> fixed summary pipeline
        - action_items -> fixed action-items pipeline
        - report -> fixed report pipeline
        - requirement_pack -> fixed requirement-pack pipeline
        - generic_task -> fallback to generic planner path
    11. routing precedence fixed:
        - semantic route first
        - structured document task second
        - generic planner path last
    """

    _banner_printed = False
    PLANNER_MODE = "deterministic_v35_3_code_chain_diff_routing"

    def __init__(
        self,
        memory_store: Any = None,
        runtime_store: Any = None,
        step_executor: Any = None,
        tool_registry: Any = None,
        workspace_dir: str = "workspace",
        workspace_root: Optional[str] = None,
        debug: bool = False,
        trace_logger: Optional[Any] = None,
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace_dir = workspace_root or workspace_dir or "workspace"
        self.debug = debug
        self.trace_logger = ensure_trace_logger(trace_logger)

        if not Planner._banner_printed:
            print("### USING PLANNER v35.3 (CODE CHAIN DIFF ROUTING + SEMANTIC ROUTING + ACTION LAYER) ###")
            Planner._banner_printed = True

    # ============================================================
    # public api
    # ============================================================

    def plan(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_input: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        context = context or {}
        text = str(user_input or context.get("user_input") or "").strip()

        self.trace_logger.log_decision(
            title="planner input",
            message=text,
            source="planner",
            raw={
                "context": context,
                "route": route,
                "kwargs": kwargs,
            },
        )

        try:
            if not text:
                result = self._build_plan_result(
                    steps=[],
                    intent="respond",
                    final_answer="空白輸入",
                    fallback_used=False,
                    error=None,
                    semantic_type="generic_task",
                    execution_route="empty_input",
                )
                self.trace_logger.log_decision(
                    title="planner result",
                    message="empty input",
                    source="planner",
                    raw=result,
                )
                return result

            semantic_steps, semantic_type, execution_route = self._plan_semantic_route(
                text=text,
                context=context,
            )
            if semantic_steps is not None:
                task_name = self._infer_task_name(
                    task_dir=str(context.get("workspace", "") or ""),
                    goal=text,
                )
                steps = self._apply_step_metadata(semantic_steps, task_name=task_name)
                intent = self._infer_intent(text=text, route=route, steps=steps)

                result = self._build_plan_result(
                    steps=steps,
                    intent=intent,
                    final_answer=f"已規劃 {len(steps)} 個步驟",
                    fallback_used=False,
                    error=None,
                    semantic_type=semantic_type,
                    execution_route=execution_route,
                )

                self.trace_logger.log_decision(
                    title="planner semantic route result",
                    message=f"steps={len(steps)}, semantic_type={semantic_type}, route={execution_route}",
                    source="planner",
                    raw={
                        "steps": steps,
                        "intent": intent,
                        "semantic_type": semantic_type,
                        "execution_route": execution_route,
                        "task_name": task_name,
                        "result": result,
                    },
                )
                return result

            structured_document_steps = self._plan_structured_document_task(
                context=context,
                route=route,
                kwargs=kwargs,
            )

            if structured_document_steps is not None:
                task_name = self._infer_task_name(
                    task_dir=str(context.get("workspace", "") or ""),
                    goal=text or "structured_document_task",
                )

                steps = self._apply_step_metadata(
                    structured_document_steps,
                    task_name=task_name,
                )
                semantic_type = self._infer_semantic_type(text=text, context=context, steps=steps)
                intent = self._infer_intent(text=text, route=route, steps=steps)

                result = self._build_plan_result(
                    steps=steps,
                    intent=intent,
                    final_answer=f"已規劃 {len(steps)} 個步驟",
                    fallback_used=False,
                    error=None,
                    semantic_type=semantic_type,
                    execution_route="structured_document_task",
                )

                self.trace_logger.log_decision(
                    title="planner structured document result",
                    message=f"steps={len(steps)}, intent={intent}, semantic_type={semantic_type}",
                    source="planner",
                    raw={
                        "steps": steps,
                        "intent": intent,
                        "semantic_type": semantic_type,
                        "task_name": task_name,
                        "result": result,
                    },
                )
                return result

            raw_steps, fallback_used = self._plan_steps(text=text, route=route, context=context)

            task_name = self._infer_task_name(
                task_dir=str(context.get("workspace", "") or ""),
                goal=text,
            )

            steps = self._apply_step_metadata(raw_steps, task_name=task_name)
            semantic_type = self._infer_semantic_type(text=text, context=context, steps=steps)
            intent = self._infer_intent(text=text, route=route, steps=steps)

            result = self._build_plan_result(
                steps=steps,
                intent=intent,
                final_answer=f"已規劃 {len(steps)} 個步驟",
                fallback_used=fallback_used,
                error=None,
                semantic_type=semantic_type,
                execution_route="generic_planner_path",
            )

            self.trace_logger.log_decision(
                title="planner result",
                message=f"steps={len(steps)}, intent={intent}, semantic_type={semantic_type}, fallback={fallback_used}",
                source="planner",
                raw={
                    "steps": steps,
                    "intent": intent,
                    "semantic_type": semantic_type,
                    "task_name": task_name,
                    "result": result,
                },
            )
            return result

        except Exception as e:
            error_message = f"planner failed: {e}"
            result = self._build_plan_result(
                steps=[],
                intent="respond",
                final_answer=error_message,
                fallback_used=False,
                error=error_message,
                semantic_type="generic_task",
                execution_route="planner_exception",
            )

            self.trace_logger.log_decision(
                title="planner exception",
                message=error_message,
                source="planner",
                raw=result,
            )
            return result

    def run(self, *args, **kwargs):
        return self.plan(*args, **kwargs)

    # ============================================================
    # structured document task
    # ============================================================

    def _plan_structured_document_task(
        self,
        context: Optional[Dict[str, Any]] = None,
        route: Any = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        return plan_structured_document_task(
            context=context,
            route=route,
            kwargs=kwargs,
            trace_logger=self.trace_logger,
        )

    # ============================================================
    # semantic routing
    # ============================================================

    def _plan_semantic_route(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, str]:
        context = context or {}
        semantic_type = self._infer_semantic_type(text=text, context=context, steps=None)

        if semantic_type == "code_chain_diff_v0":
            parsed = self._match_code_chain_diff_v0_task(text=text)

            # Code Chain v0.3 must not silently fall through to the generic
            # planner when the user clearly asks for a diff / patch. The
            # generic action layer may otherwise reinterpret the request as a
            # normal write_file task and overwrite the source file.
            if parsed is None:
                parsed = self._fallback_match_code_chain_diff_v0_task(text=text)

            if parsed is None:
                return None, semantic_type, "code_chain_diff_v0_unmatched"

            steps = self._build_code_chain_diff_v0_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
                instruction=parsed.get("instruction", ""),
            )
            return steps, semantic_type, "code_chain_diff_v0_pipeline"

        if semantic_type == "code_chain_v0":
            parsed = self._match_code_chain_v0_task(text=text)
            if parsed is None:
                return None, semantic_type, "code_chain_v0_unmatched"

            steps = self._build_code_chain_v0_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
                instruction=parsed.get("instruction", ""),
            )
            return steps, semantic_type, "code_chain_v0_pipeline"

        if semantic_type == "semantic_chain_v0":
            parsed = self._match_semantic_chain_v0_task(text=text)
            if parsed is None:
                return None, semantic_type, "semantic_chain_v0_unmatched"

            steps = self._build_semantic_chain_v0_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
            )
            return steps, semantic_type, "semantic_chain_v0_pipeline"

        if semantic_type == "summary":
            parsed = self._match_semantic_document_task(text=text, semantic_type="summary")
            if parsed is None:
                return None, semantic_type, "semantic_summary_unmatched"

            steps = self._build_semantic_document_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
                llm_mode="summary",
                prompt=self._build_semantic_summary_prompt(parsed["source_path"]),
            )
            return steps, semantic_type, "semantic_summary_pipeline"

        if semantic_type == "action_items":
            parsed = self._match_semantic_document_task(text=text, semantic_type="action_items")
            if parsed is None:
                return None, semantic_type, "semantic_action_items_unmatched"

            steps = self._build_semantic_document_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
                llm_mode="action_items",
                prompt=self._build_semantic_action_items_prompt(parsed["source_path"]),
            )
            return steps, semantic_type, "semantic_action_items_pipeline"

        if semantic_type == "report":
            parsed = self._match_semantic_document_task(text=text, semantic_type="report")
            if parsed is None:
                return None, semantic_type, "semantic_report_unmatched"

            steps = self._build_semantic_document_pipeline(
                source_path=parsed["source_path"],
                output_path=parsed["output_path"],
                llm_mode="report",
                prompt=self._build_semantic_report_prompt(parsed["source_path"]),
            )
            return steps, semantic_type, "semantic_report_pipeline"

        if semantic_type == "requirement_pack":
            parsed = self._match_requirement_pack_task(text=text)
            if parsed is None:
                return None, semantic_type, "semantic_requirement_pack_unmatched"

            steps = self._build_requirement_pack_pipeline(source_path=parsed["source_path"])
            return steps, semantic_type, "semantic_requirement_pack_pipeline"

        if semantic_type == "git_pipeline_task":
            return self._build_git_pipeline_steps(context=context), semantic_type, "git_pipeline_path"

        return None, semantic_type, "generic_planner_path"

    def _infer_semantic_type(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        context = context or {}

        explicit = str(
            context.get("semantic_type")
            or context.get("task_type")
            or context.get("mode")
            or ""
        ).strip().lower()

        normalized_explicit = self._normalize_semantic_type(explicit)
        if normalized_explicit != "generic_task":
            return normalized_explicit

        lowered = str(text or "").strip().lower()

        if self._looks_like_code_chain_diff_v0(lowered):
            return "code_chain_diff_v0"

        if self._looks_like_code_chain_v0(lowered):
            return "code_chain_v0"

        if self._looks_like_semantic_chain_v0(lowered):
            return "semantic_chain_v0"

        if any(token in lowered for token in ["requirement-pack", "requirement pack"]):
            return "requirement_pack"

        if self._looks_like_git_pipeline_task(lowered):
            return "git_pipeline_task"

        if "project_summary.txt" in lowered and "implementation_plan.txt" in lowered and "acceptance_checklist.txt" in lowered:
            return "requirement_pack"

        if any(token in lowered for token in ["action items", "action-items", "action_items", "extract actions", "todo list"]):
            return "action_items"

        if any(token in lowered for token in ["summarize", "summary", "make summary", "create summary"]):
            return "summary"

        if any(token in lowered for token in ["generate report", "create report", "write report", "report from"]):
            return "report"

        if isinstance(steps, list) and len(steps) >= 3:
            first_type = str(steps[0].get("type") or "").strip().lower()
            second_type = str(steps[1].get("type") or "").strip().lower()
            third_type = str(steps[2].get("type") or "").strip().lower()
            if first_type == "read_file" and second_type == "llm" and third_type == "write_file":
                llm_mode = str(steps[1].get("mode") or "").strip().lower()
                normalized_mode = self._normalize_semantic_type(llm_mode)
                if normalized_mode != "generic_task":
                    return normalized_mode

        return "generic_task"

    def _normalize_semantic_type(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        if lowered in {"code_chain_diff_v0", "code-chain-diff-v0", "code chain diff v0", "code_chain_v0_diff", "code-chain-v0-diff", "diff_mode", "patch_mode", "code patch"}:
            return "code_chain_diff_v0"
        if lowered in {"code_chain_v0", "code-chain-v0", "code chain v0", "controlled_code_edit", "controlled-code-edit"}:
            return "code_chain_v0"
        if lowered in {"semantic_chain_v0", "semantic-chain-v0", "semantic chain v0", "summary_action_items", "summary-action-items"}:
            return "semantic_chain_v0"
        if lowered in {"summary", "summarize"}:
            return "summary"
        if lowered in {"action_items", "action-items", "actionitems"}:
            return "action_items"
        if lowered in {"report", "generate_report"}:
            return "report"
        if lowered in {"requirement_pack", "requirement-pack", "requirement pack"}:
            return "requirement_pack"
        if lowered in {"git_pipeline_task", "git-pipeline-task", "git pipeline task", "git_pipeline"}:
            return "git_pipeline_task"
        return "generic_task"

    def _looks_like_git_pipeline_task(self, lowered: str) -> bool:
        text = str(lowered or "").strip().lower()
        if not text:
            return False

        has_pr_token = bool(re.search(r"\bpr\b", text))
        has_git_signal = any(token in text for token in ["git diff", "git status", "commit message", "github"])
        has_pipeline_signal = (
            has_pr_token
            or any(token in text for token in ["pipeline", "outbox", "pull request", "commit message"])
        )
        has_generation_signal = any(token in text for token in ["generate", "create", "prepare", "analyze", "產生", "生成", "分析"])

        if "git_pipeline_task" in text or "git_pipeline_path" in text:
            return True

        if "commit message" in text and (has_pr_token or "pull request" in text or "outbox" in text):
            return True

        if "git diff" in text and has_pipeline_signal:
            return True

        return has_git_signal and has_pipeline_signal and has_generation_signal

    def _looks_like_code_chain_diff_v0(self, lowered: str) -> bool:
        text = str(lowered or "").strip().lower()
        if not text:
            return False

        has_diff_signal = any(
            token in text
            for token in [
                "code chain v0.3",
                "code_chain_v0_3",
                "code chain diff",
                "diff mode",
                "patch mode",
                "generate diff",
                "create diff",
                "make diff",
                "unified diff",
                "generate patch",
                "create patch",
                "make patch",
                "產生 diff",
                "產生 patch",
            ]
        )

        # Strong signal: any explicit .patch/.diff target should be treated as
        # a diff task before generic write handling gets a chance to consume it.
        has_patch_or_diff_file = bool(re.search(r"[^\s,;]+\.(?:patch|diff)\b", text, flags=re.IGNORECASE))

        has_code_file = bool(
            re.search(
                r"(?:workspace|shared|sandbox)[\\/][^\s,;]+\.(?:py|js|ts|tsx|jsx|html|css|json|yaml|yml|md|txt)",
                text,
                flags=re.IGNORECASE,
            )
            or re.search(r"[^\s,;]+\.(?:py|js|ts|tsx|jsx|html|css)", text, flags=re.IGNORECASE)
        )
        has_read_signal = any(token in text for token in ["read ", "讀", "讀取"])
        has_edit_signal = any(
            token in text
            for token in [
                "add comments",
                "add comment",
                "add docstring",
                "rewrite",
                "modify",
                "update",
                "edit",
                "refactor",
                "fix",
                "改寫",
                "修改",
                "修正",
                "重構",
            ]
        )

        return bool(
            has_diff_signal
            or (has_patch_or_diff_file and has_code_file)
            or (has_code_file and has_read_signal and has_edit_signal and has_patch_or_diff_file)
        )

    def _match_code_chain_diff_v0_task(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()
        if not self._looks_like_code_chain_diff_v0(lowered):
            return None

        output_path = self._detect_patch_output_path_from_text(stripped)
        if not output_path:
            output_path = self._detect_output_path_from_text(stripped, llm_mode="code_chain_diff_v0")

        if not output_path:
            return None

        normalized_output = output_path.replace("\\", "/").lower()
        if not normalized_output.endswith((".patch", ".diff")):
            return None

        source_path = self._detect_source_path_from_text(stripped, output_path=output_path)
        if not source_path:
            source_path = self._detect_source_code_path_from_text(stripped, output_path=output_path)

        if not source_path:
            read_match = re.search(r"\bread\s+([^\s,;]+)", stripped, flags=re.IGNORECASE)
            if read_match:
                source_path = self._normalize_requested_path(read_match.group(1))

        if not source_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
            "instruction": self._extract_code_chain_instruction(stripped),
        }

    def _fallback_match_code_chain_diff_v0_task(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()
        if not stripped:
            return None

        has_diff_intent = any(
            token in lowered
            for token in [
                "diff",
                "patch",
                "unified diff",
                "產生 diff",
                "產生 patch",
            ]
        )
        if not has_diff_intent:
            return None

        output_path = self._detect_patch_output_path_from_text(stripped)
        if not output_path:
            return None

        source_path = self._detect_source_code_path_from_text(stripped, output_path=output_path)
        if not source_path:
            source_path = self._detect_source_path_from_text(stripped, output_path=output_path)

        if not source_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
            "instruction": self._extract_code_chain_instruction(stripped),
        }

    def _detect_patch_output_path_from_text(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()
        candidates = re.findall(
            r"(?:[A-Za-z]:[\\/][^\s,;]+|(?:workspace|shared|sandbox)[\\/][^\s,;]+|[^\s,;]+\.(?:patch|diff))",
            stripped,
            flags=re.IGNORECASE,
        )
        for candidate in candidates:
            normalized = self._normalize_requested_path(candidate)
            if normalized.replace("\\", "/").lower().endswith((".patch", ".diff")):
                return normalized
        return None

    def _detect_source_code_path_from_text(self, text: str, output_path: str = "") -> Optional[str]:
        stripped = str(text or "").strip()
        normalized_output = self._normalize_requested_path(output_path).replace("\\", "/") if output_path else ""
        candidates = re.findall(
            r"(?:[A-Za-z]:[\\/][^\s,;]+|(?:workspace|shared|sandbox)[\\/][^\s,;]+|[^\s,;]+\.(?:py|js|ts|tsx|jsx|html|css|json|yaml|yml|md|txt))",
            stripped,
            flags=re.IGNORECASE,
        )
        for candidate in candidates:
            normalized = self._normalize_requested_path(candidate)
            normalized_slash = normalized.replace("\\", "/")
            if normalized_slash == normalized_output:
                continue
            if normalized_slash.lower().endswith((".patch", ".diff")):
                continue
            if normalized:
                return normalized
        return None

    def _build_code_chain_diff_v0_pipeline(self, source_path: str, output_path: str, instruction: str = "") -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "code_chain_diff_v0",
                "prompt": self._build_code_chain_diff_v0_prompt(source_path=source_path, instruction=instruction),
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
            {
                "type": "verify_unified_diff",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
            },
            {
                "type": "apply_unified_diff",
                "patch_path": output_path,
                "target_path": source_path,
                "scope": self._infer_path_scope(source_path),
            },
        ]

        if self._should_add_python_syntax_verification(source_path):
            steps.append(
                {
                    "type": "verify_python_syntax",
                    "path": source_path,
                    "scope": self._infer_path_scope(source_path),
                }
            )

        return steps

    def _build_code_chain_diff_v0_prompt(self, source_path: str, instruction: str = "") -> str:
        edit_instruction = str(instruction or "Generate a minimal unified diff for the requested controlled code edit.").strip()
        return (
            "You are performing Code Chain v0.3: controlled single-file unified-diff generation.\n\n"
            "Rules:\n"
            "1. Use ONLY the source code below.\n"
            "2. Return a valid unified diff only.\n"
            "3. Do not return the full rewritten file.\n"
            "4. Do not use Markdown fences.\n"
            "5. Do not include explanations outside the diff.\n"
            "6. The diff must contain --- and +++ file headers and at least one @@ hunk.\n"
            "7. Preserve existing public behavior unless the request explicitly changes it.\n"
            "8. Do not claim that the file is unavailable.\n"
            "9. Do not ask the user for the file again.\n\n"
            f"Source path: {source_path}\n"
            f"Edit instruction: {edit_instruction}\n\n"
            "Source code:\n"
            "{{file_content}}"
        )

    def _looks_like_code_chain_v0(self, lowered: str) -> bool:
        text = str(lowered or "").strip().lower()
        if not text:
            return False

        has_chain_signal = any(
            token in text
            for token in [
                "code chain v0",
                "code_chain_v0",
                "controlled code edit",
                "controlled-code-edit",
            ]
        )
        has_code_file = bool(
            re.search(
                r"(?:workspace|shared|sandbox)[\\/][^\s,;]+\.(?:py|js|ts|tsx|jsx|html|css|json|yaml|yml|md|txt)",
                text,
                flags=re.IGNORECASE,
            )
            or re.search(r"[^\s,;]+\.(?:py|js|ts|tsx|jsx|html|css)", text, flags=re.IGNORECASE)
        )
        has_read_signal = any(token in text for token in ["read ", "讀", "讀取"])
        has_edit_signal = any(
            token in text
            for token in [
                "rewrite",
                "modify",
                "update",
                "edit",
                "refactor",
                "fix",
                "add comments",
                "add docstring",
                "改寫",
                "修改",
                "修正",
                "重構",
            ]
        )
        has_output_signal = bool(re.search(r"\bto\s+[^\s,;]+", text, flags=re.IGNORECASE)) or "輸出" in text

        return has_chain_signal or (has_code_file and has_read_signal and has_edit_signal and has_output_signal)

    def _match_code_chain_v0_task(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()
        if not self._looks_like_code_chain_v0(lowered):
            return None

        output_path = self._detect_output_path_from_text(stripped, llm_mode="code_chain_v0")
        if not output_path:
            return None

        source_path = self._detect_source_path_from_text(stripped, output_path=output_path)
        if not source_path:
            read_match = re.search(r"\bread\s+([^\s,;]+)", stripped, flags=re.IGNORECASE)
            if read_match:
                source_path = self._normalize_requested_path(read_match.group(1))

        if not source_path:
            return None

        normalized_source = source_path.replace("\\", "/")
        normalized_output = output_path.replace("\\", "/")

        # v0 safety: never overwrite the source file. Write a controlled output copy.
        if normalized_source == normalized_output:
            return None

        # v0 safety: write target must stay in workspace/shared or shared.
        if not (normalized_output.startswith("workspace/shared/") or normalized_output.startswith("shared/")):
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
            "instruction": self._extract_code_chain_instruction(stripped),
        }

    def _extract_code_chain_instruction(self, text: str) -> str:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        if "add comments" in lowered or "add docstring" in lowered:
            return "Add concise explanatory comments/docstrings where useful without changing behavior."
        if "refactor" in lowered or "重構" in lowered:
            return "Refactor for readability while preserving behavior."
        if "fix" in lowered or "修正" in lowered:
            return "Fix the code issue described by the request while preserving unrelated behavior."
        if "rewrite" in lowered or "改寫" in lowered:
            return "Rewrite the code cleanly while preserving behavior."
        if "modify" in lowered or "edit" in lowered or "update" in lowered or "修改" in lowered:
            return "Modify the code according to the request while preserving unrelated behavior."

        return "Apply the requested controlled code edit while preserving behavior and public interfaces."

    def _build_code_chain_v0_pipeline(self, source_path: str, output_path: str, instruction: str = "") -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "code_chain_v0",
                "prompt": self._build_code_chain_v0_prompt(source_path=source_path, instruction=instruction),
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
        ]

        if self._should_add_python_syntax_verification(output_path):
            steps.append(
                {
                    "type": "verify_python_syntax",
                    "path": output_path,
                    "scope": self._infer_path_scope(output_path),
                }
            )

        return steps

    def _should_add_python_syntax_verification(self, output_path: str) -> bool:
        normalized = str(output_path or "").replace("\\", "/").strip().lower()
        if not normalized.endswith(".py"):
            return False
        return normalized.startswith("workspace/shared/") or normalized.startswith("shared/")

    def _build_code_chain_v0_prompt(self, source_path: str, instruction: str = "") -> str:
        edit_instruction = str(instruction or "Apply the requested controlled code edit while preserving behavior.").strip()
        return (
            "You are performing Code Chain v0: a controlled single-file code rewrite.\n\n"
            "Rules:\n"
            "1. Use ONLY the source code below.\n"
            "2. Return the complete rewritten file content only.\n"
            "3. Do not use Markdown fences.\n"
            "4. Do not include explanations outside the code.\n"
            "5. Preserve existing public behavior unless the request explicitly changes it.\n"
            "6. Do not claim that the file is unavailable.\n"
            "7. Do not ask the user for the file again.\n\n"
            f"Source path: {source_path}\n"
            f"Edit instruction: {edit_instruction}\n\n"
            "Source code:\n"
            "{{file_content}}"
        )

    def _looks_like_semantic_chain_v0(self, lowered: str) -> bool:
        text = str(lowered or "").strip().lower()
        if not text:
            return False

        has_summary_signal = any(
            token in text
            for token in [
                "summarize",
                "summary",
                "make summary",
                "create summary",
                "摘要",
                "總結",
            ]
        )
        has_action_signal = any(
            token in text
            for token in [
                "action items",
                "action-items",
                "action_items",
                "extract actions",
                "todo list",
                "todos",
                "待辦",
                "行動項目",
            ]
        )
        has_chain_signal = any(
            token in text
            for token in [
                "semantic chain v0",
                "semantic_chain_v0",
                "summary and action",
                "summary + action",
                "summary then action",
                "summarize then extract",
            ]
        )

        return (has_summary_signal and has_action_signal) or has_chain_signal

    def _match_semantic_chain_v0_task(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()
        if not self._looks_like_semantic_chain_v0(lowered):
            return None

        output_path = self._detect_output_path_from_text(stripped, llm_mode="semantic_chain_v0")
        if not output_path:
            output_path = "workspace/shared/semantic_chain_v0.txt"

        source_path = self._detect_source_path_from_text(stripped, output_path=output_path)
        if not source_path:
            read_match = re.search(r"\bread\s+([^\s,;]+)", stripped, flags=re.IGNORECASE)
            if read_match:
                source_path = self._normalize_requested_path(read_match.group(1))

        if not source_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
        }

    def _build_semantic_chain_v0_pipeline(self, source_path: str, output_path: str) -> List[Dict[str, Any]]:
        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "summary",
                "prompt": self._build_semantic_summary_prompt(source_path),
            },
            {
                "type": "llm",
                "mode": "action_items",
                "prompt": self._build_semantic_chain_v0_action_items_prompt(source_path),
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
        ]

    def _match_semantic_document_task(
        self,
        text: str,
        semantic_type: str,
    ) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        output_path = self._detect_output_path_from_text(stripped, llm_mode=semantic_type)
        source_path = self._detect_source_path_from_text(stripped, output_path=output_path or "")

        if not source_path:
            return None

        if not output_path:
            if semantic_type == "summary":
                output_path = "workspace/shared/summary.txt"
            elif semantic_type == "action_items":
                output_path = "workspace/shared/action_items.txt"
            elif semantic_type == "report":
                output_path = "workspace/shared/report.txt"

        if not output_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
        }

    def _match_requirement_pack_task(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        if "project_summary.txt" not in lowered or "implementation_plan.txt" not in lowered or "acceptance_checklist.txt" not in lowered:
            return None

        source_path = self._detect_source_path_from_text(stripped, output_path="")
        if not source_path:
            read_match = re.search(r"\bread\s+([^\s,;]+)", stripped, flags=re.IGNORECASE)
            if read_match:
                source_path = self._normalize_requested_path(read_match.group(1))

        if not source_path:
            return None

        return {"source_path": source_path}

    def _build_semantic_document_pipeline(
        self,
        source_path: str,
        output_path: str,
        llm_mode: str,
        prompt: str,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": llm_mode,
                "prompt": prompt,
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
        ]

    def _build_requirement_pack_pipeline(self, source_path: str) -> List[Dict[str, Any]]:
        project_summary_path = "workspace/shared/project_summary.txt"
        implementation_plan_path = "workspace/shared/implementation_plan.txt"
        acceptance_checklist_path = "workspace/shared/acceptance_checklist.txt"

        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "project_summary",
                "prompt": self._build_requirement_project_summary_prompt(source_path),
            },
            {
                "type": "write_file",
                "path": project_summary_path,
                "scope": self._infer_path_scope(project_summary_path),
                "content": "{{previous_result}}",
            },
            {
                "type": "llm",
                "mode": "implementation_plan",
                "prompt": self._build_requirement_implementation_plan_prompt(source_path),
            },
            {
                "type": "write_file",
                "path": implementation_plan_path,
                "scope": self._infer_path_scope(implementation_plan_path),
                "content": "{{previous_result}}",
            },
            {
                "type": "llm",
                "mode": "acceptance_checklist",
                "prompt": self._build_requirement_acceptance_checklist_prompt(source_path),
            },
            {
                "type": "write_file",
                "path": acceptance_checklist_path,
                "scope": self._infer_path_scope(acceptance_checklist_path),
                "content": "{{previous_result}}",
            },
        ]

    def _build_git_pipeline_steps(self, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        context = context or {}
        tool_input: Dict[str, Any] = {}
        for key in ("repo_root", "workspace_root", "cwd", "workspace"):
            value = context.get(key)
            if value:
                tool_input[key] = value

        return [
            {
                "type": "tool",
                "tool_name": "git_pipeline",
                "tool_input": tool_input,
            }
        ]

    def _build_semantic_summary_prompt(self, source_path: str) -> str:
        return (
            "Summarize the following document into a concise plain-text summary.\n\n"
            "Rules:\n"
            "1. Keep it clear and short.\n"
            "2. Do not use JSON.\n"
            "3. Do not add extra commentary.\n\n"
            f"Document content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    def _build_semantic_action_items_prompt(self, source_path: str) -> str:
        return (
            "Extract action items from the following document as concise plain text.\n\n"
            "Rules:\n"
            "1. Focus on actionable tasks only.\n"
            "2. Prefer bullet-style plain text.\n"
            "3. Do not use JSON.\n\n"
            f"Document content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    def _build_semantic_chain_v0_action_items_prompt(self, source_path: str) -> str:
        return (
            "Create a Semantic Chain v0 output from the previous summary below.\n\n"
            "Required output format:\n"
            "Summary:\n"
            "- Rewrite the provided summary in 1-3 concise bullets.\n\n"
            "Action Items:\n"
            "- Extract concrete action items only. If no concrete action items exist, write: - No concrete action items found.\n\n"
            "Rules:\n"
            "1. Use only the content below.\n"
            "2. Do not claim that the file is unavailable.\n"
            "3. Do not ask the user to provide the text again.\n"
            "4. Keep the output plain text.\n\n"
            f"Source path: {source_path}\n\n"
            "Input summary from previous step:\n"
            "{{previous_result}}"
        )

    def _build_semantic_report_prompt(self, source_path: str) -> str:
        return (
            "Generate a concise structured report from the following document.\n\n"
            "Rules:\n"
            "1. Use plain text.\n"
            "2. Include brief sections for summary, key points, and next steps.\n"
            "3. Do not use JSON.\n\n"
            f"Document content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    def _build_requirement_project_summary_prompt(self, source_path: str) -> str:
        return (
            "Create project_summary.txt from the requirement document below.\n\n"
            "Rules:\n"
            "1. Use plain text only.\n"
            "2. Start with the heading: Project Summary\n"
            "3. Keep it concise and engineering-oriented.\n"
            "4. Include goal, scope, and expected outputs.\n"
            "5. Mention project_summary.txt, implementation_plan.txt, and acceptance_checklist.txt explicitly.\n\n"
            f"Requirement content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    def _build_requirement_implementation_plan_prompt(self, source_path: str) -> str:
        return (
            "Create implementation_plan.txt from the requirement document below.\n\n"
            "Rules:\n"
            "1. Use plain text only.\n"
            "2. Start with the heading: Implementation Plan\n"
            "3. Make it practical and engineering-oriented.\n"
            "4. Include phases, concrete steps, and expected deliverables.\n"
            "5. Mention project_summary.txt, implementation_plan.txt, and acceptance_checklist.txt explicitly.\n\n"
            f"Requirement content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    def _build_requirement_acceptance_checklist_prompt(self, source_path: str) -> str:
        return (
            "Create acceptance_checklist.txt from the requirement document below.\n\n"
            "Rules:\n"
            "1. Use plain text only.\n"
            "2. Start with the heading: Acceptance Checklist\n"
            "3. The output must include these section headings exactly:\n"
            "   - Acceptance Criteria\n"
            "   - Verification\n"
            "   - Deliverable\n"
            "4. Keep it clear and checklist-oriented.\n"
            "5. Mention project_summary.txt, implementation_plan.txt, and acceptance_checklist.txt explicitly when relevant.\n\n"
            f"Requirement content:\n{{{{file_content}}}}\n\nSource path: {source_path}"
        )

    # ============================================================
    # core planning
    # ============================================================

    def _plan_steps(
        self,
        text: str,
        route: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        stripped = str(text or "").strip()

        looks_multi_clause = len(self._split_clauses(stripped)) > 1
        early_verify = None
        if not looks_multi_clause and self._has_verify_intent(stripped):
            early_verify = self._extract_verify_request(stripped, last_path=None)

        if early_verify:
            verify_path = str(early_verify.get("path") or "").strip()
            self.trace_logger.log_decision(
                title="early verify detected",
                message=verify_path or stripped,
                source="planner",
                raw={"step": early_verify},
            )
            return [early_verify], False

        special_document_steps = self._plan_document_flow(stripped)
        if special_document_steps is not None:
            return special_document_steps, False

        multi_steps = self._plan_multi_step_task(stripped)
        if multi_steps is not None:
            self.trace_logger.log_decision(
                title="multi-step detected",
                message=stripped,
                source="planner",
                raw={"steps": multi_steps},
            )
            return multi_steps, False

        clauses = self._split_clauses(text)

        self.trace_logger.log_decision(
            title="split clauses",
            message=f"{len(clauses)} clauses",
            source="planner",
            raw={"clauses": clauses},
        )

        steps: List[Dict[str, Any]] = []
        fallback_used = False
        last_path: Optional[str] = None

        for clause in clauses:
            sub_steps, clause_fallback_used, last_path = self._plan_single_clause(
                text=clause,
                route=route,
                last_path=last_path,
                context=context,
            )
            if clause_fallback_used:
                fallback_used = True
            steps.extend(sub_steps)

        return steps, fallback_used

    # ============================================================
    # document flow
    # ============================================================

    def _plan_document_flow(self, text: str) -> Optional[List[Dict[str, Any]]]:
        return plan_document_flow(
            text=text,
            trace_logger=self.trace_logger,
        )

    # ============================================================
    # multi-step task planning
    # ============================================================

    def _plan_multi_step_task(self, text: str) -> Optional[List[Dict[str, Any]]]:
        chain_v0 = self._match_semantic_chain_v0_task(text)
        if chain_v0 is not None:
            return self._build_semantic_chain_v0_pipeline(
                source_path=chain_v0["source_path"],
                output_path=chain_v0["output_path"],
            )

        parsed = self._match_read_transform_write(text)
        if parsed is None:
            return None

        source_path = parsed["source_path"]
        output_path = parsed["output_path"]
        llm_mode = parsed["llm_mode"]

        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": llm_mode,
                "prompt": self._build_transform_prompt(llm_mode=llm_mode, source_path=source_path),
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
        ]

    def _match_read_transform_write(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        llm_mode = self._detect_transform_mode(lowered)
        if llm_mode is None:
            return None

        output_path = self._detect_output_path_from_text(stripped, llm_mode=llm_mode)
        if not output_path:
            return None

        source_path = self._detect_source_path_from_text(stripped, output_path=output_path)
        if not source_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
            "llm_mode": llm_mode,
        }

    def _detect_transform_mode(self, lowered: str) -> Optional[str]:
        if any(token in lowered for token in ["bullet points", "bullet-point", "bullets", "bullet list"]):
            return "bullet_points"
        if any(token in lowered for token in ["rewrite", "reword", "polish", "convert", "transform"]):
            return "rewrite"
        if any(token in lowered for token in ["action items", "action-items", "todo list", "extract actions"]):
            return "action_items"
        if any(token in lowered for token in ["summarize", "summary", "make summary", "create summary"]):
            return "summary"
        if any(token in lowered for token in ["generate report", "create report", "write report", "report from"]):
            return "report"
        return None

    def _detect_output_path_from_text(self, text: str, llm_mode: str) -> Optional[str]:
        stripped = str(text or "").strip()

        if llm_mode == "code_chain_diff_v0":
            patch_output = self._detect_patch_output_path_from_text(stripped)
            if patch_output:
                return patch_output

        patterns = [
            r"\bto\s+([^\s,;]+)",
            r"\binto\s+([^\s,;]+)",
            r"\bas\s+([^\s,;]+)",
            r"\bwrite\s+(?:to\s+)?([^\s,;]+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = self._normalize_requested_path(match.group(1))
            if self._looks_like_file_candidate(candidate):
                return candidate

        if llm_mode == "summary":
            return "workspace/shared/summary.txt"
        if llm_mode == "semantic_chain_v0":
            return "workspace/shared/semantic_chain_v0.txt"
        if llm_mode == "action_items":
            return "workspace/shared/action_items.txt"
        if llm_mode == "report":
            return "workspace/shared/report.txt"
        return None

    def _detect_source_path_from_text(self, text: str, output_path: str) -> Optional[str]:
        raw_candidates = re.findall(
            r"(?:[A-Za-z]:[\\/][^\s,;]+|(?:workspace|shared|sandbox)[\\/][^\s,;]+|[^\s,;]+\.(?:txt|md|json|log|csv|py|js|ts|tsx|jsx|html|css|yaml|yml))",
            text,
            flags=re.IGNORECASE,
        )

        normalized_candidates: List[str] = []
        for candidate in raw_candidates:
            normalized = self._normalize_requested_path(candidate)
            if normalized and normalized not in normalized_candidates:
                normalized_candidates.append(normalized)

        for candidate in normalized_candidates:
            if candidate != output_path:
                return candidate

        read_match = re.search(r"\bread\s+([^\s,;]+)", text, flags=re.IGNORECASE)
        if read_match:
            candidate = self._normalize_requested_path(read_match.group(1))
            if candidate and candidate != output_path:
                return candidate

        summarize_match = re.search(
            r"\b(?:summarize|summary|action items from|extract actions from|generate report from|report from)\s+([^\s,;]+)",
            text,
            flags=re.IGNORECASE,
        )
        if summarize_match:
            candidate = self._normalize_requested_path(summarize_match.group(1))
            if candidate and candidate != output_path:
                return candidate

        return None

    def _build_transform_prompt(self, llm_mode: str, source_path: str) -> str:
        if llm_mode == "summary":
            instruction = "Summarize the following document into concise plain text."
        elif llm_mode == "action_items":
            instruction = "Extract action items from the following document as concise plain text."
        elif llm_mode == "report":
            instruction = "Generate a concise structured report from the following document."
        elif llm_mode == "bullet_points":
            instruction = "Rewrite the following document as concise bullet points while preserving the original meaning."
        elif llm_mode == "rewrite":
            instruction = "Rewrite the following document clearly while preserving the original meaning."
        else:
            instruction = "Process the following document."

        return (
            f"{instruction}\n\n"
            "Rules:\n"
            "1. Use the document content below as the only source.\n"
            "2. Do not claim that the file is unavailable.\n"
            "3. Do not ask the user to provide the text again.\n"
            "4. Keep the output plain text.\n\n"
            f"Source path: {source_path}\n\n"
            "Document content:\n"
            "{{file_content}}"
        )

    # ============================================================
    # per-clause planning
    # ============================================================

    def _plan_single_clause(
        self,
        text: str,
        route: Any = None,
        last_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        self.trace_logger.log_decision(
            title="analyze clause",
            message=stripped,
            source="planner",
            raw={"last_path": last_path},
        )

        if not stripped:
            return [], False, last_path

        action_steps, action_last_path = self._plan_action_clause(
            text=stripped,
            lowered=lowered,
            last_path=last_path,
            context=context,
        )
        if action_steps is not None:
            self.trace_logger.log_decision(
                title="action layer detected",
                message=stripped,
                source="planner",
                raw={
                    "steps": action_steps,
                    "last_path": action_last_path,
                },
            )
            return action_steps, False, action_last_path

        cmd = self._extract_command(stripped)
        if cmd:
            self.trace_logger.log_decision(
                title="command detected",
                message=cmd,
                source="planner",
            )
            return [self._make_command_step(command=cmd, context=context)], False, last_path

        run_python = self._extract_run_python_request(stripped)
        if run_python:
            self.trace_logger.log_decision(
                title="run_python detected",
                message=str(run_python.get("path") or ""),
                source="planner",
                raw=run_python,
            )
            run_path = str(run_python.get("path") or "").strip() or last_path
            if run_path:
                run_python["path"] = run_path
            return [run_python], False, run_python.get("path") or last_path

        verify = self._extract_verify_request(stripped, last_path=last_path)
        if verify:
            verify_path = str(verify.get("path") or "").strip() or last_path
            self.trace_logger.log_decision(
                title="verify detected",
                message=verify_path or "",
                source="planner",
                raw=verify,
            )
            if verify_path:
                verify["path"] = verify_path
            return [verify], False, verify_path or last_path

        write = self._extract_write_request(stripped)
        if write:
            current_path = str(write.get("path") or "").strip() or last_path
            content = write.get("content", "")
            has_explicit_content = bool(write.get("has_explicit_content", False))

            if has_explicit_content:
                normalized_step = {
                    "type": "write_file",
                    "path": current_path or "",
                    "scope": self._infer_path_scope(current_path or ""),
                    "content": content,
                }
                step_type = "write detected"
            else:
                normalized_step = {
                    "type": "ensure_file",
                    "path": current_path or "",
                    "scope": self._infer_path_scope(current_path or ""),
                }
                step_type = "ensure_file detected"

            self.trace_logger.log_decision(
                title=step_type,
                message=normalized_step.get("path", ""),
                source="planner",
                raw=normalized_step,
            )
            return [normalized_step], False, current_path

        if self._looks_like_read(stripped):
            read_path = self._resolve_read_path(stripped, last_path=last_path)
            if read_path:
                self.trace_logger.log_decision(
                    title="read detected",
                    message=read_path,
                    source="planner",
                    raw={
                        "text": stripped,
                        "resolved_from_last_path": self._extract_file_path(stripped) is None and last_path is not None,
                    },
                )
                return [{"type": "read_file", "path": read_path}], False, read_path

        if self._looks_like_search(stripped):
            self.trace_logger.log_decision(
                title="search detected",
                message=stripped,
                source="planner",
            )
            return [{"type": "web_search", "query": stripped}], False, last_path

        self.trace_logger.log_decision(
            title="fallback detected",
            message=stripped,
            source="planner",
            raw={
                "reason": "no deterministic rule matched",
                "last_path": last_path,
            },
        )
        return [{"type": "llm", "prompt": stripped}], True, last_path

    # ============================================================
    # action layer
    # ============================================================

    def _plan_action_clause(
        self,
        text: str,
        lowered: str,
        last_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        append_request = self._match_append_file_request(text)
        if append_request is not None:
            path = append_request["path"]
            content = append_request["content"]
            return [
                {
                    "type": "append_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                }
            ], path

        explicit_write = self._match_write_file_request(text)
        if explicit_write is not None:
            path = explicit_write["path"]
            content = explicit_write["content"]

            return [
                {
                    "type": "ensure_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                },
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                },
            ], path

        command_request = self._match_command_request(text)
        if command_request is not None:
            return [self._make_command_step(command=command_request, context=context)], last_path

        python_request = self._match_run_python_request(text)
        if python_request is not None:
            return [
                {
                    "type": "run_python",
                    "path": python_request,
                }
            ], python_request

        hello_shortcut = self._match_hello_file_shortcut(lowered)
        if hello_shortcut is not None:
            path, content = hello_shortcut
            return [
                {
                    "type": "ensure_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                },
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                },
            ], path

        create_empty = self._match_create_empty_file_request(text)
        if create_empty is not None:
            return [
                {
                    "type": "ensure_file",
                    "path": create_empty,
                    "scope": self._infer_path_scope(create_empty),
                }
            ], create_empty

        append_write = self._match_write_into_existing_request(text, last_path=last_path)
        if append_write is not None:
            path = append_write["path"]
            content = append_write["content"]
            return [
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                }
            ], path

        return None, last_path

    def _repo_root_from_context(self, context: Optional[Dict[str, Any]] = None) -> str:
        if not isinstance(context, dict):
            return ""

        for key in (
            "target_repo_root",
            "target_repo",
            "repo_root",
            "repository_root",
            "project_root",
            "command_cwd",
            "cwd_override",
            "cwd",
        ):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        route = context.get("route")
        if isinstance(route, dict):
            for key in (
                "target_repo_root",
                "target_repo",
                "repo_root",
                "repository_root",
                "project_root",
                "cwd",
            ):
                value = route.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _make_command_step(
        self,
        command: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        step = {
            "type": "command",
            "command": str(command or "").strip(),
        }
        repo_root = self._repo_root_from_context(context)
        if repo_root:
            step["command_cwd"] = repo_root
            step["target_repo_root"] = repo_root
        return step

    def _match_hello_file_shortcut(self, lowered: str) -> Optional[Tuple[str, str]]:
        candidates = {
            "write hello file",
            "create hello file",
            "make hello file",
            "write a hello file",
            "create a hello file",
            "make a hello file",
        }
        if lowered in candidates:
            return "workspace/shared/hello.txt", "hello"
        return None

    def _match_command_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:run|execute|do)\s+command\s*:\s*(.+)$",
            r"^(?:run|execute)\s+this\s+command\s*:\s*(.+)$",
            r"^(?:cmd|command)\s*:\s*(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if match:
                command = str(match.group(1) or "").strip()
                if command:
                    return command

        return None

    def _match_run_python_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:run|execute)\s+python\s+file\s+(.+\.py)$",
            r"^(?:run|execute)\s+(.+\.py)$",
            r"^python\s+(.+\.py)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if match:
                path = str(match.group(1) or "").strip()
                if path:
                    return path

        return None

    def _match_create_empty_file_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:create|make|ensure)\s+file\s+(.+)$",
            r"^(?:create|make|ensure)\s+an?\s+empty\s+file\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            raw_path = str(match.group(1) or "").strip()
            path = self._normalize_requested_path(raw_path)
            if path:
                return path

        return None

    def _match_append_file_request(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:append)\s+(.+?)\s+to\s+(.+)$",
            r"^(?:append)\s+(.+?)\s+into\s+(.+)$",
            r"^(?:add)\s+(.+?)\s+to\s+(.+)$",
            r"^(?:add)\s+line\s+(.+?)\s+to\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            content = self._strip_wrapping_quotes(str(match.group(1) or "").strip())
            path = self._normalize_requested_path(str(match.group(2) or "").strip())

            if path and content:
                return {
                    "path": path,
                    "content": content,
                }

        return None

    def _match_write_file_request(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:write|create|make)\s+file\s+(.+?)\s+with\s+content\s+(.+)$",
            r"^(?:write|create|make)\s+(.+?)\s+with\s+content\s+(.+)$",
            r"^(?:write|save)\s+(.+?)\s+to\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            left = str(match.group(1) or "").strip()
            right = str(match.group(2) or "").strip()

            if " to " in stripped.lower() and pattern.endswith(r"\s+to\s+(.+)$"):
                content = left
                path = self._normalize_requested_path(right)
            else:
                path = self._normalize_requested_path(left)
                content = self._strip_wrapping_quotes(right)

            if path and content != "":
                return {
                    "path": path,
                    "content": content,
                }

        return None

    def _match_write_into_existing_request(self, text: str, last_path: Optional[str]) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:write|save)\s+(.+)$",
            r"^(?:put)\s+(.+)\s+into\s+file$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            content = self._strip_wrapping_quotes(str(match.group(1) or "").strip())
            if content and last_path:
                return {
                    "path": last_path,
                    "content": content,
                }

        return None

    def _normalize_requested_path(self, raw_path: str) -> str:
        candidate = self._strip_wrapping_quotes(str(raw_path or "").strip())
        candidate = candidate.replace("\\", "/").strip()

        if not candidate:
            return ""

        if candidate.startswith("workspace/") or candidate.startswith("shared/") or candidate.startswith("sandbox/"):
            return candidate

        if re.match(r"^[A-Za-z]:/", candidate):
            return candidate

        if "/" in candidate:
            return candidate

        return f"workspace/shared/{candidate}"

    def _strip_wrapping_quotes(self, text: str) -> str:
        value = str(text or "").strip()
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
        return value

    def _looks_like_file_candidate(self, value: str) -> bool:
        lowered = str(value or "").strip().lower()
        return lowered.endswith((".txt", ".md", ".json", ".log", ".csv", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".yaml", ".yml"))

    # ============================================================
    # result builder / contract normalization
    # ============================================================

    def _build_plan_result(
        self,
        steps: List[Dict[str, Any]],
        intent: str,
        final_answer: str,
        fallback_used: bool,
        error: Optional[str],
        semantic_type: str = "generic_task",
        execution_route: str = "generic_planner_path",
    ) -> Dict[str, Any]:
        normalized_steps = self._normalize_steps(steps)

        result = {
            "ok": error is None,
            "planner_mode": self.PLANNER_MODE,
            "intent": str(intent or "respond"),
            "semantic_type": str(semantic_type or "generic_task"),
            "execution_route": str(execution_route or "generic_planner_path"),
            "final_answer": str(final_answer or ""),
            "steps": normalized_steps,
            "error": error,
            "meta": {
                "fallback_used": bool(fallback_used),
                "step_count": len(normalized_steps),
                "semantic_type": str(semantic_type or "generic_task"),
                "execution_route": str(execution_route or "generic_planner_path"),
            },
        }

        return result

    def _normalize_steps(self, steps: Any) -> List[Dict[str, Any]]:
        if not isinstance(steps, list):
            return []

        normalized: List[Dict[str, Any]] = []
        fallback_task_name = self._infer_task_name(task_dir="", goal="planner_steps")

        for idx, step in enumerate(steps, start=1):
            normalized.append(
                self._normalize_step(
                    step=step,
                    index=idx,
                    fallback_task_name=fallback_task_name,
                )
            )

        return normalized

    def _normalize_step(
        self,
        step: Any,
        index: int,
        fallback_task_name: str,
    ) -> Dict[str, Any]:
        if isinstance(step, dict):
            item = dict(step)
        else:
            item = {"type": "unknown", "value": step}

        step_type = str(item.get("type") or "unknown").strip() or "unknown"
        task_name = str(item.get("task_name") or fallback_task_name).strip() or fallback_task_name
        step_id = str(item.get("id") or f"{task_name}_step_{index}").strip() or f"{task_name}_step_{index}"

        normalized = dict(item)
        normalized["type"] = step_type
        normalized["task_name"] = task_name
        normalized["id"] = step_id

        if step_type in {"read_file", "write_file", "append_file", "ensure_file", "run_python", "verify_file", "verify_python_syntax", "verify_unified_diff"}:
            normalized["path"] = str(normalized.get("path") or "")

        if step_type == "command":
            normalized["command"] = str(normalized.get("command") or "")

        if step_type == "web_search":
            normalized["query"] = str(normalized.get("query") or "")

        if step_type == "tool":
            normalized["tool_name"] = str(normalized.get("tool_name") or normalized.get("tool") or "")
            tool_input = normalized.get("tool_input")
            if not isinstance(tool_input, dict):
                tool_input = {}
            normalized["tool_input"] = tool_input

        if step_type == "llm":
            normalized["prompt"] = str(normalized.get("prompt") or "")
            normalized["mode"] = str(normalized.get("mode") or "")

        if step_type == "write_file":
            normalized["content"] = str(normalized.get("content") or "")
            normalized["scope"] = str(normalized.get("scope") or self._infer_path_scope(normalized.get("path", "")))

        if step_type == "append_file":
            normalized["content"] = str(normalized.get("content") or "")
            normalized["scope"] = str(normalized.get("scope") or self._infer_path_scope(normalized.get("path", "")))

        if step_type == "ensure_file":
            normalized["scope"] = str(normalized.get("scope") or self._infer_path_scope(normalized.get("path", "")))

        return normalized

    # ============================================================
    # clause splitting
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        normalized = str(text or "").strip()

        parts = re.split(
            r"(?:，|,|。|；|;|\n+|\r\n+|然後|接著|之後|再來|再|and then|then)",
            normalized,
            flags=re.IGNORECASE,
        )

        cleaned = [p.strip() for p in parts if p and p.strip()]
        return cleaned

    # ============================================================
    # deterministic rule parser adapter
    # ============================================================

    def _extract_command(self, text: str) -> Optional[str]:
        return extract_command(text)

    def _extract_run_python_request(self, text: str) -> Optional[Dict[str, Any]]:
        return extract_run_python_request(text)

    def _infer_path_scope(self, path: str) -> str:
        return infer_path_scope(path)

    def _has_verify_intent(self, text: str) -> bool:
        return has_verify_intent(text)

    def _extract_verify_request(self, text: str, last_path: Optional[str]) -> Optional[Dict[str, Any]]:
        return extract_verify_request(text, last_path)

    def _extract_file_path(self, text: str) -> Optional[str]:
        return extract_file_path(text)

    def _looks_like_read(self, text: str) -> bool:
        return looks_like_read(text)

    def _resolve_read_path(self, text: str, last_path: Optional[str]) -> Optional[str]:
        return resolve_read_path(text, last_path)

    def _extract_write_request(self, text: str) -> Optional[Dict[str, Any]]:
        return extract_write_request(text)

    def _looks_like_search(self, text: str) -> bool:
        return looks_like_search(text)

    # ============================================================
    # metadata
    # ============================================================

    def _infer_task_name(self, task_dir: str, goal: str) -> str:
        _ = task_dir
        safe_goal = str(goal or "task")
        return "task_" + hashlib.sha1(safe_goal.encode("utf-8")).hexdigest()[:6]

    def _apply_step_metadata(self, steps: List[Dict[str, Any]], task_name: str) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            item = dict(step or {})
            item.setdefault("id", f"{task_name}_step_{idx}")
            item.setdefault("task_name", task_name)
            item.setdefault("type", "unknown")
            enriched.append(item)

        return enriched

    def _infer_intent(self, text: str, route: Any, steps: List[Dict[str, Any]]) -> str:
        _ = text
        _ = route

        if not steps:
            return "respond"

        first_type = str(steps[0].get("type") or "").strip().lower()

        if len(steps) >= 3:
            second_type = str(steps[1].get("type") or "").strip().lower()
            third_type = str(steps[2].get("type") or "").strip().lower()

            if first_type == "read_file" and second_type == "llm" and third_type == "write_file":
                llm_mode = str(steps[1].get("mode") or "").strip().lower()
                normalized_mode = self._normalize_semantic_type(llm_mode)
                if normalized_mode != "generic_task":
                    return normalized_mode

        if len(steps) >= 7:
            if first_type == "read_file":
                second_type = str(steps[1].get("type") or "").strip().lower()
                third_type = str(steps[2].get("type") or "").strip().lower()
                last_type = str(steps[-1].get("type") or "").strip().lower()
                if second_type == "llm" and third_type == "write_file" and last_type == "write_file":
                    first_mode = str(steps[1].get("mode") or "").strip().lower()
                    if first_mode == "project_summary":
                        return "requirement_pack"

        return first_type or "unknown"


# ============================================================
# ZERO v7.0.0 - Planner-driven Autonomous Repair Loop shim
# ============================================================
# This compatibility shim keeps the existing Planner class intact and adds one
# narrow autonomous repair route:
#   Analyze workspace/shared/code_chain_probe.py and repair broken math functions
# It intentionally does not introduce broad autonomous edits.

_ZERO_V7_ORIGINAL_PLAN_SEMANTIC_ROUTE = Planner._plan_semantic_route


def _zero_v7_extract_workspace_py_path(text: str) -> str:
    match = re.search(r"(workspace[/\\][A-Za-z0-9_./\\ -]+?\.py)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/")


def _zero_v7_looks_like_autonomous_repair(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    if "workspace/" not in lowered or ".py" not in lowered:
        return False
    has_analyze = any(token in lowered for token in ("analyze", "inspect", "check", "diagnose", "分析", "檢查"))
    has_repair = any(token in lowered for token in ("repair", "fix", "correct", "修復", "修正"))
    has_code_target = any(token in lowered for token in ("function", "functions", "math", "code", "函數"))
    return has_analyze and has_repair and has_code_target


def _zero_v7_plan_semantic_route(self, text: str, context: Optional[Dict[str, Any]] = None):
    if _zero_v7_looks_like_autonomous_repair(text):
        target_path = _zero_v7_extract_workspace_py_path(text)
        if target_path:
            step = {
                "type": "code_chain_repair",
                "task_text": str(text or "").strip(),
                "target_path": target_path,
                "planner_autonomous_repair": True,
                "repair_scope": "single_file_math_functions_minimal",
                "description": "Planner-driven autonomous code repair through Code Chain",
            }
            return [step], "autonomous_code_repair_v0", "planner_autonomous_repair_code_chain"
    return _ZERO_V7_ORIGINAL_PLAN_SEMANTIC_ROUTE(self, text=text, context=context)


Planner._plan_semantic_route = _zero_v7_plan_semantic_route
Planner.PLANNER_MODE = "deterministic_v35_3_plus_v7_0_0_autonomous_repair_loop"


# ============================================================
# ZERO v7.0.2 - Planner repair step preservation reinforcement
# ============================================================
# Purpose:
# - Ensure autonomous repair intent returns a code_chain_repair step in both
#   semantic routing and generic step planning paths.

_ZERO_V702_ORIGINAL_PLANNER_PLAN_STEPS = Planner._plan_steps


def _zero_v702_planner_plan_steps(self, text: str, route: Any = None):
    if _zero_v7_looks_like_autonomous_repair(text):
        target_path = _zero_v7_extract_workspace_py_path(text)
        if target_path:
            return [
                {
                    "type": "code_chain_repair",
                    "task_text": str(text or "").strip(),
                    "target_path": target_path,
                    "planner_autonomous_repair": True,
                    "repair_scope": "single_file_math_functions_minimal",
                    "description": "Planner-driven autonomous code repair through Code Chain",
                    "preserve_step_type": True,
                }
            ], False
    return _ZERO_V702_ORIGINAL_PLANNER_PLAN_STEPS(self, text=text, route=route)


Planner._plan_steps = _zero_v702_planner_plan_steps
Planner.PLANNER_MODE = "deterministic_v35_3_plus_v7_0_2_repair_step_preservation"


# ZERO v7.0.3 marker: autonomous repair planner emits registered code_chain_repair steps.


# ============================================================
# ZERO v7.1.0 - Planner Repair Scope Preflight Guard
# ============================================================
# Planner-side reinforcement. AgentLoop performs the primary preflight before
# task creation; this keeps direct Planner callers from emitting executable
# code_chain_repair steps for missing or protected paths.

import os as _zero_v710_os
from pathlib import Path as _ZeroV710Path

_ZERO_V710_ORIGINAL_PLAN_SEMANTIC_ROUTE = Planner._plan_semantic_route
_ZERO_V710_ORIGINAL_PLAN_STEPS = Planner._plan_steps


def _zero_v710_planner_normalize_path_text(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v710_planner_extract_any_py_path(text: str) -> str:
    match = re.search(
        r"((?:workspace|core|services|tests|ui)[/\\][A-Za-z0-9_./\\ -]+?\.py|app\.py|system_boot\.py)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _zero_v710_planner_normalize_path_text(match.group(1))


def _zero_v710_planner_looks_like_repair_intent(text: str) -> bool:
    lowered = str(text or "").strip().lower().replace("\\", "/")
    if not lowered or ".py" not in lowered:
        return False
    has_analyze = any(token in lowered for token in ("analyze", "inspect", "check", "diagnose", "分析", "檢查"))
    has_repair = any(token in lowered for token in ("repair", "fix", "correct", "修復", "修正"))
    has_code_target = any(token in lowered for token in ("function", "functions", "math", "code", "函數", "函式", "程式"))
    return has_analyze and has_repair and has_code_target


def _zero_v710_planner_repair_scope_decision(text: str) -> Dict[str, Any]:
    target_path = _zero_v710_planner_extract_any_py_path(text)
    if not target_path:
        return {"ok": False, "error": "missing_target_path", "reason": "repair request is missing an explicit Python target path", "target_path": ""}
    normalized = _zero_v710_planner_normalize_path_text(target_path)
    lowered = normalized.lower()
    protected = (
        lowered == "app.py"
        or lowered == "system_boot.py"
        or lowered.startswith("core/")
        or lowered.startswith("services/")
        or lowered.startswith("tests/")
        or lowered.startswith("ui/")
    )
    if protected:
        return {"ok": False, "error": "repair_scope_blocked", "reason": f"blocked by repair scope guard: {normalized}", "target_path": normalized}
    if not normalized.startswith("workspace/shared/") or not normalized.endswith(".py"):
        return {"ok": False, "error": "repair_scope_blocked", "reason": f"autonomous repair requires workspace/shared/*.py target: {normalized}", "target_path": normalized}
    try:
        repo_root = _ZeroV710Path.cwd().resolve()
        target = (repo_root / normalized).resolve()
        target.relative_to(repo_root)
    except Exception:
        return {"ok": False, "error": "path_escapes_repo_root", "reason": f"repair target escapes repo root: {normalized}", "target_path": normalized}
    if not target.exists():
        return {"ok": False, "error": "file_not_found", "reason": f"file not found: {normalized}", "target_path": normalized}
    return {"ok": True, "error": None, "reason": "repair scope preflight passed", "target_path": normalized}


def _zero_v710_planner_make_failed_repair_step(text: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    target_path = str(decision.get("target_path") or "").strip()
    reason = str(decision.get("reason") or decision.get("error") or "repair preflight failed")
    return {
        "type": "code_chain_repair_preflight_failed",
        "task_text": str(text or "").strip(),
        "target_path": target_path,
        "planner_autonomous_repair": True,
        "repair_scope_guard": True,
        "error": str(decision.get("error") or "repair_preflight_failed"),
        "reason": reason,
        "description": "Autonomous repair blocked before Code Chain execution",
    }


def _zero_v710_planner_plan_semantic_route(self, text: str, context: Optional[Dict[str, Any]] = None):
    if _zero_v710_planner_looks_like_repair_intent(text):
        decision = _zero_v710_planner_repair_scope_decision(text)
        if not bool(decision.get("ok")):
            return [
                _zero_v710_planner_make_failed_repair_step(text, decision)
            ], "autonomous_code_repair_v0", "repair_scope_preflight_failed"
    return _ZERO_V710_ORIGINAL_PLAN_SEMANTIC_ROUTE(self, text=text, context=context)


def _zero_v710_planner_plan_steps(self, text: str, route: Any = None):
    if _zero_v710_planner_looks_like_repair_intent(text):
        decision = _zero_v710_planner_repair_scope_decision(text)
        if not bool(decision.get("ok")):
            return [_zero_v710_planner_make_failed_repair_step(text, decision)], False
    return _ZERO_V710_ORIGINAL_PLAN_STEPS(self, text=text, route=route)


Planner._plan_semantic_route = _zero_v710_planner_plan_semantic_route
Planner._plan_steps = _zero_v710_planner_plan_steps
Planner.PLANNER_MODE = "deterministic_v35_3_plus_v7_1_0_repair_scope_guard"


# ============================================================
# ZERO v7.3.0 - Autonomous Multi-Step Repair Chain
# ============================================================
# Purpose:
# - Keep v7.1 repair scope preflight.
# - Expand planner-driven repair from a single code_chain_repair step into:
#     1) code_chain_verify
#     2) code_chain_repair
#     3) apply_patch
#     4) code_chain_verify
# - Do not broaden target scope; still only workspace/shared/*.py.

_ZERO_V730_ORIGINAL_PLAN_SEMANTIC_ROUTE = Planner._plan_semantic_route
_ZERO_V730_ORIGINAL_PLAN_STEPS = Planner._plan_steps


def _zero_v730_planner_build_repair_chain_steps(text: str, target_path: str) -> List[Dict[str, Any]]:
    task_text = str(text or "").strip()
    target_path = _zero_v710_planner_normalize_path_text(target_path)
    return [
        {
            "type": "code_chain_verify",
            "task_text": task_text,
            "target_path": target_path,
            "planner_autonomous_repair": True,
            "repair_scope": "single_file_math_functions_minimal",
            "continue_on_failure": True,
            "description": "Verify target code before autonomous Code Chain repair",
            "preserve_step_type": True,
        },
        {
            "type": "code_chain_repair",
            "task_text": task_text,
            "target_path": target_path,
            "planner_autonomous_repair": True,
            "repair_scope": "single_file_math_functions_minimal",
            "description": "Apply planner-driven autonomous code repair through Code Chain",
            "preserve_step_type": True,
        },
        {
            "type": "apply_patch",
            "task_text": task_text,
            "target_path": target_path,
            "planner_autonomous_repair": True,
            "repair_scope": "single_file_math_functions_minimal",
            "description": "Apply validated edit payload produced by Code Chain repair",
            "preserve_step_type": True,
        },
        {
            "type": "code_chain_verify",
            "task_text": task_text,
            "target_path": target_path,
            "planner_autonomous_repair": True,
            "repair_scope": "single_file_math_functions_minimal",
            "description": "Verify target code after autonomous Code Chain repair",
            "preserve_step_type": True,
        },
    ]


def _zero_v730_planner_plan_semantic_route(self, text: str, context: Optional[Dict[str, Any]] = None):
    if _zero_v710_planner_looks_like_repair_intent(text):
        decision = _zero_v710_planner_repair_scope_decision(text)
        if not bool(decision.get("ok")):
            return [
                _zero_v710_planner_make_failed_repair_step(text, decision)
            ], "autonomous_code_repair_v0", "repair_scope_preflight_failed"
        return (
            _zero_v730_planner_build_repair_chain_steps(text, str(decision.get("target_path") or "")),
            "autonomous_code_repair_v1_multistep",
            "planner_autonomous_multistep_repair_code_chain",
        )
    return _ZERO_V730_ORIGINAL_PLAN_SEMANTIC_ROUTE(self, text=text, context=context)


def _zero_v730_planner_plan_steps(
    self,
    text: str,
    route: Any = None,
    context: Optional[Dict[str, Any]] = None,
):
    if _zero_v710_planner_looks_like_repair_intent(text):
        decision = _zero_v710_planner_repair_scope_decision(text)
        if not bool(decision.get("ok")):
            return [_zero_v710_planner_make_failed_repair_step(text, decision)], False
        return _zero_v730_planner_build_repair_chain_steps(text, str(decision.get("target_path") or "")), False
    try:
        return _ZERO_V730_ORIGINAL_PLAN_STEPS(self, text=text, route=route, context=context)
    except TypeError as exc:
        if "unexpected keyword argument 'context'" not in str(exc):
            raise
        return _ZERO_V730_ORIGINAL_PLAN_STEPS(self, text=text, route=route)


Planner._plan_semantic_route = _zero_v730_planner_plan_semantic_route
Planner._plan_steps = _zero_v730_planner_plan_steps
Planner.PLANNER_MODE = "deterministic_v35_3_plus_v7_3_0_autonomous_multistep_repair_chain"
