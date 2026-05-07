from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RepairAction:
    type: str
    path: str
    content: str = ""
    reason: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepairPlan:
    ok: bool
    classification: str
    summary: str
    reason: str = ""
    confidence: float = 0.0
    actions: List[RepairAction] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["actions"] = [action.to_dict() for action in self.actions]
        return payload


class RepairPlanner:
    """
    ZERO AER Repair Planner v0.2

    Deterministic repair planner before LLM repair is connected.

    Main v0.2 fix:
    - Parse/load the source file from the failed py_compile command.
    - Repair incomplete binary expressions such as:
          return a +
      into:
          return a + b
    """

    def plan(
        self,
        *,
        step_result: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
        source_path: str = "",
        source_text: str = "",
        target_path: str = "",
    ) -> RepairPlan:
        observation = self._normalize_observation(step_result=step_result, previous_result=previous_result)

        command = str(observation.get("command") or "")
        combined = "\n".join(
            str(x)
            for x in [
                observation.get("error_type", ""),
                observation.get("message", ""),
                observation.get("stderr", ""),
                observation.get("stdout", ""),
                command,
            ]
            if str(x).strip()
        )

        resolved_source_path = self._clean_path(
            source_path
            or observation.get("path", "")
            or observation.get("resolved_path", "")
        )

        if not source_text:
            source_text = self._load_source_text_from_observation(
                observation=observation,
                source_path=resolved_source_path,
                command=command,
            )

        if self._looks_like_python_failure(combined):
            return self._plan_python_repair(
                combined=combined,
                source_text=source_text,
                source_path=resolved_source_path,
                target_path=target_path,
                observation=observation,
            )

        return RepairPlan(
            ok=False,
            classification="unsupported_failure",
            summary="No deterministic repair rule matched.",
            reason="repair planner v0.2 handles common Python compile failures only",
            diagnostics={
                "observation": observation,
                "combined": combined[-4000:],
                "source_text_present": bool(source_text),
                "source_path": resolved_source_path,
            },
        )

    def plan_from_runtime_state(
        self,
        *,
        runtime_state: Dict[str, Any],
        source_path: str = "",
        source_text: str = "",
        target_path: str = "",
    ) -> RepairPlan:
        last_step_result = runtime_state.get("last_step_result")
        previous_result = runtime_state.get("last_result") or runtime_state.get("last_observation")
        return self.plan(
            step_result=last_step_result if isinstance(last_step_result, dict) else None,
            previous_result=previous_result,
            source_path=source_path,
            source_text=source_text,
            target_path=target_path,
        )

    def analyze_failure(
        self,
        *,
        step: Optional[Dict[str, Any]] = None,
        step_result: Optional[Dict[str, Any]] = None,
        runtime_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_path = ""
        target_path = ""

        if isinstance(step, dict):
            source_path = str(step.get("path") or "").strip()
            target_path = str(step.get("repair_target_path") or step.get("target_path") or "").strip()

        state = runtime_state if isinstance(runtime_state, dict) else {}
        previous_result = state.get("last_step_result") if isinstance(state.get("last_step_result"), dict) else None

        return self.plan(
            step_result=step_result,
            previous_result=previous_result,
            source_path=source_path,
            target_path=target_path,
        ).to_dict()

    # ============================================================
    # Python repair
    # ============================================================

    def _plan_python_repair(
        self,
        *,
        combined: str,
        source_text: str,
        source_path: str,
        target_path: str,
        observation: Dict[str, Any],
    ) -> RepairPlan:
        output_path = self._repair_output_path(source_path=source_path, target_path=target_path)
        fixed_text, meta = self._repair_common_python_syntax(source_text)

        if fixed_text and fixed_text != source_text:
            return RepairPlan(
                ok=True,
                classification="python_syntax_error",
                summary="Detected Python compile/syntax failure and produced a repaired candidate.",
                reason=str(meta.get("rule") or "common_python_syntax"),
                confidence=float(meta.get("confidence") or 0.8),
                actions=[
                    RepairAction(
                        type="write_file",
                        path=output_path,
                        content=fixed_text,
                        reason="write repaired Python candidate",
                        confidence=float(meta.get("confidence") or 0.8),
                        metadata={
                            "source_path": source_path,
                            "target_path": output_path,
                            "repair_rule": meta.get("rule"),
                            "repair_meta": meta,
                        },
                    )
                ],
                diagnostics={
                    "observation": observation,
                    "combined": combined[-4000:],
                    "source_text_present": bool(source_text),
                    "source_preview": source_text[-1000:] if isinstance(source_text, str) else "",
                },
            )

        return RepairPlan(
            ok=False,
            classification="python_syntax_error",
            summary="Detected Python failure, but no deterministic safe repair was produced.",
            reason="no safe source rewrite matched",
            confidence=0.0,
            actions=[],
            diagnostics={
                "observation": observation,
                "combined": combined[-4000:],
                "source_text_present": bool(source_text),
                "source_preview": source_text[-1000:] if isinstance(source_text, str) else "",
            },
        )

    def _repair_common_python_syntax(self, source_text: str) -> Tuple[str, Dict[str, Any]]:
        if not isinstance(source_text, str) or not source_text.strip():
            return "", {"rule": "no_source_text", "confidence": 0.0}

        text = source_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        repaired: List[str] = []
        hits: List[Dict[str, Any]] = []

        for line_no, original_line in enumerate(lines, start=1):
            stripped_right = original_line.rstrip()
            stripped_left = stripped_right.lstrip()
            indent = stripped_right[: len(stripped_right) - len(stripped_left)]

            # def add(a,b):
            #     return a +
            # -> return a + b
            m = re.match(
                r"^(\s*)return\s+([A-Za-z_][A-Za-z0-9_]*)\s*([\+\-\*/])\s*$",
                stripped_right,
            )
            if m:
                lhs = m.group(2)
                op = m.group(3)
                rhs = self._guess_rhs_symbol(source_text=text, lhs=lhs)
                new_line = f"{indent}return {lhs} {op} {rhs}"
                repaired.append(new_line)
                hits.append(
                    {
                        "rule": "repair_incomplete_return_binary_expression",
                        "line": line_no,
                        "lhs": lhs,
                        "operator": op,
                        "rhs": rhs,
                        "before": original_line,
                        "after": new_line,
                    }
                )
                continue

            # x = a +
            m = re.match(
                r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*([\+\-\*/])\s*$",
                stripped_right,
            )
            if m:
                target = m.group(2)
                lhs = m.group(3)
                op = m.group(4)
                rhs = self._guess_rhs_symbol(source_text=text, lhs=lhs)
                new_line = f"{indent}{target} = {lhs} {op} {rhs}"
                repaired.append(new_line)
                hits.append(
                    {
                        "rule": "repair_incomplete_assignment_binary_expression",
                        "line": line_no,
                        "target": target,
                        "lhs": lhs,
                        "operator": op,
                        "rhs": rhs,
                        "before": original_line,
                        "after": new_line,
                    }
                )
                continue

            if self._looks_like_missing_colon(stripped_right):
                new_line = stripped_right + ":"
                repaired.append(new_line)
                hits.append(
                    {
                        "rule": "repair_missing_colon",
                        "line": line_no,
                        "before": original_line,
                        "after": new_line,
                    }
                )
                continue

            repaired.append(original_line)

        if not hits:
            return source_text, {"rule": "no_common_syntax_rule_matched", "confidence": 0.0}

        repaired_text = "\n".join(repaired).rstrip("\n") + "\n"
        return repaired_text, {
            "rule": "+".join(hit["rule"] for hit in hits[:3]),
            "confidence": 0.84 if any(hit["rule"] == "repair_incomplete_return_binary_expression" for hit in hits) else 0.65,
            "hits": hits,
        }

    def _looks_like_missing_colon(self, line: str) -> bool:
        stripped = str(line or "").strip()
        if not stripped or stripped.endswith(":") or stripped.startswith("#"):
            return False
        return bool(
            re.match(
                r"^(def|class|if|elif|else|for|while|try|except|finally|with)\b.*[^:]$",
                stripped,
            )
        )

    def _guess_rhs_symbol(self, *, source_text: str, lhs: str) -> str:
        args = self._extract_first_function_args(source_text)
        if args:
            if lhs in args:
                idx = args.index(lhs)
                if idx + 1 < len(args):
                    return args[idx + 1]
            for arg in args:
                if arg != lhs:
                    return arg
            return args[-1]

        if lhs in {"a", "x", "left"}:
            return "b"
        return "0"

    def _extract_first_function_args(self, source_text: str) -> List[str]:
        m = re.search(r"def\s+\w+\s*\(([^)]*)\)\s*:?", source_text)
        if not m:
            return []

        args: List[str] = []
        for raw in m.group(1).split(","):
            item = raw.strip()
            if not item:
                continue
            item = item.split("=")[0].strip()
            item = item.split(":")[0].strip()
            if item in {"self", "cls", "*args", "**kwargs"}:
                continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", item):
                args.append(item)
        return args

    # ============================================================
    # Source loading
    # ============================================================

    def _load_source_text_from_observation(
        self,
        *,
        observation: Dict[str, Any],
        source_path: str,
        command: str,
    ) -> str:
        for candidate in self._candidate_source_paths(observation=observation, source_path=source_path, command=command):
            if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass

        for key in ("source_text", "content", "text"):
            value = observation.get(key)
            if isinstance(value, str) and value.strip():
                return value

        return ""

    def _candidate_source_paths(self, *, observation: Dict[str, Any], source_path: str, command: str) -> List[str]:
        candidates: List[str] = []

        def add(value: Any) -> None:
            text = self._clean_path(value)
            if text and text not in candidates:
                candidates.append(text)

        add(source_path)
        add(observation.get("path"))
        add(observation.get("resolved_path"))

        cwd = self._clean_path(observation.get("cwd") or observation.get("effective_cwd"))
        command_path = self._extract_py_compile_target(command or observation.get("command", ""))
        if command_path:
            add(command_path)
            if cwd and not os.path.isabs(command_path):
                add(os.path.join(cwd, command_path))

        return candidates

    def _extract_py_compile_target(self, command: str) -> str:
        text = str(command or "").strip()
        m = re.search(r"(?:^|\s)-m\s+py_compile\s+(.+)$", text)
        if not m:
            return ""

        tail = m.group(1).strip()
        if not tail:
            return ""

        return tail.split()[0].strip().strip('"').strip("'")

    # ============================================================
    # Observation normalization
    # ============================================================

    def _normalize_observation(self, *, step_result: Optional[Dict[str, Any]], previous_result: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}

        if isinstance(previous_result, dict):
            payload.update(self._flatten_result(previous_result))

        if isinstance(step_result, dict):
            payload.update(self._flatten_result(step_result))

        if not payload and isinstance(previous_result, str):
            payload["message"] = previous_result

        payload.setdefault("stdout", "")
        payload.setdefault("stderr", "")
        payload.setdefault("message", "")
        payload.setdefault("error_type", "")
        return payload

    def _flatten_result(self, value: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}

        def set_if_text(key: str, candidate: Any) -> None:
            if candidate is None:
                return
            text = str(candidate)
            if text and key not in payload:
                payload[key] = text

        for key in ("stdout", "stderr", "message", "final_answer", "command", "path", "resolved_path", "cwd", "effective_cwd", "source_text", "content", "text"):
            set_if_text("message" if key == "final_answer" else key, value.get(key))

        error = value.get("error")
        if isinstance(error, dict):
            set_if_text("error_type", error.get("type"))
            set_if_text("message", error.get("message"))
        elif error is not None:
            set_if_text("message", error)

        result = value.get("result")
        if isinstance(result, dict):
            nested = self._flatten_result(result)
            for key, item in nested.items():
                payload.setdefault(key, item)

        return payload

    def _looks_like_python_failure(self, text: str) -> bool:
        lowered = str(text or "").lower()
        return (
            "syntaxerror" in lowered
            or "invalid syntax" in lowered
            or "py_compile" in lowered
            or "python_failed" in lowered
            or "python failed" in lowered
        )

    def _repair_output_path(self, *, source_path: str, target_path: str) -> str:
        clean_target = self._clean_path(target_path)
        if clean_target:
            return os.path.basename(clean_target) or "repair_candidate.py"

        clean_source = self._clean_path(source_path)
        if clean_source:
            base = os.path.basename(clean_source)
            if base.endswith(".py"):
                return base[:-3] + "_repaired.py"
            return base + ".repaired"

        return "repair_candidate.py"

    def _clean_path(self, value: Any) -> str:
        return str(value or "").strip().strip('"').strip("'")


def plan_repair(
    *,
    step_result: Optional[Dict[str, Any]] = None,
    previous_result: Any = None,
    source_path: str = "",
    source_text: str = "",
    target_path: str = "",
) -> Dict[str, Any]:
    return RepairPlanner().plan(
        step_result=step_result,
        previous_result=previous_result,
        source_path=source_path,
        source_text=source_text,
        target_path=target_path,
    ).to_dict()
