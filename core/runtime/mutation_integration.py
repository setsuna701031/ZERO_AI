from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from core.runtime.mutation_boundary import MutationBoundary, MutationBoundaryError


MUTATION_STEP_TYPES = {
    "apply_patch",
    "apply_unified_diff",
    "code_chain_repair",
    "autonomous_code_repair",
    "repo_edit",
    "repo_apply",
}


class MutationRuntimeIntegration:
    """
    ZERO Mutation Boundary runtime integration adapter.

    Purpose:
    - Keep TaskRunner / StepExecutor integration small and explicit.
    - Detect mutation-like steps.
    - Build preview payloads from step dictionaries.
    - Run the governed mutation lifecycle when the actual apply result is already
      produced by the guarded executor.
    - Return a normalized mutation boundary payload that can be stored inside
      execution_log / repair_context / audit records.

    This adapter deliberately does NOT:
    - modify files by itself,
    - run commands by itself,
    - bypass ExecutionGuard,
    - replace StepExecutor,
    - replace TaskRuntime.

    Safe integration shape:

        step_result = StepExecutor.execute(step)
        mutation_result = integration.record_after_step(
            step=step,
            step_result=step_result,
            verification_result=...,
            replay_result=...,
        )

    In v1.3 this can be used as a bridge without restructuring the existing
    runtime files.
    """

    def __init__(
        self,
        workspace_root: str = "workspace",
        project_root: Optional[str] = None,
        boundary: Optional[MutationBoundary] = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.boundary = boundary or MutationBoundary(
            workspace_root=workspace_root,
            project_root=project_root,
        )

    # ============================================================
    # detection
    # ============================================================

    def is_mutation_step(self, step: Dict[str, Any]) -> bool:
        step = step if isinstance(step, dict) else {}
        step_type = str(step.get("type") or "").strip().lower()
        if step_type in MUTATION_STEP_TYPES:
            return True

        action = str(step.get("action") or "").strip().lower()
        if action in MUTATION_STEP_TYPES:
            return True

        if isinstance(step.get("edit_payload"), dict):
            return True

        if step.get("patch") or step.get("diff") or step.get("unified_diff"):
            return True

        return False

    def extract_target_files(self, step: Dict[str, Any], step_result: Optional[Dict[str, Any]] = None) -> List[str]:
        step = step if isinstance(step, dict) else {}
        step_result = step_result if isinstance(step_result, dict) else {}

        candidates: List[str] = []

        for key in ("target_path", "target", "path", "file_path"):
            value = step.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

        edit_payload = step.get("edit_payload")
        if isinstance(edit_payload, dict):
            changed_files = edit_payload.get("changed_files")
            if isinstance(changed_files, list):
                candidates.extend(str(item).strip() for item in changed_files if str(item).strip())

            for list_key in ("file_edits", "edits", "patches"):
                items = edit_payload.get(list_key)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            for key in ("target_path", "target", "path", "file_path"):
                                value = item.get(key)
                                if isinstance(value, str) and value.strip():
                                    candidates.append(value.strip())

        for result_key in ("changed_files", "target_files"):
            values = step_result.get(result_key)
            if isinstance(values, list):
                candidates.extend(str(item).strip() for item in values if str(item).strip())

        result_payload = step_result.get("result")
        if isinstance(result_payload, dict):
            for result_key in ("changed_files", "target_files"):
                values = result_payload.get(result_key)
                if isinstance(values, list):
                    candidates.extend(str(item).strip() for item in values if str(item).strip())

        normalized: List[str] = []
        for item in candidates:
            text = str(item or "").strip().replace("\\", "/").strip("/")
            text = text.lstrip("./")
            if not text:
                continue
            # If an existing step uses workspace/shared/foo.py as a project-style
            # mutation target, keep it as-is.  MutationBoundary will still validate
            # it as relative and will block traversal / unsafe paths.
            normalized.append(text)

        return list(dict.fromkeys(normalized))

    def build_preview_payload(
        self,
        step: Dict[str, Any],
        step_result: Optional[Dict[str, Any]] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        step = step if isinstance(step, dict) else {}
        step_result = step_result if isinstance(step_result, dict) else {}

        step_type = str(step.get("type") or step.get("action") or "mutation").strip() or "mutation"
        target_files = self.extract_target_files(step, step_result)

        proposed_changes: List[Dict[str, Any]] = []
        edit_payload = step.get("edit_payload")
        if isinstance(edit_payload, dict):
            raw_edits = edit_payload.get("file_edits")
            if not isinstance(raw_edits, list):
                raw_edits = edit_payload.get("edits")
            if isinstance(raw_edits, list):
                for item in raw_edits:
                    if isinstance(item, dict):
                        proposed_changes.append(copy.deepcopy(item))

        if not proposed_changes:
            for key in ("patch", "diff", "unified_diff"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    proposed_changes.append(
                        {
                            "kind": key,
                            "preview": self._truncate_text(value, 2000),
                        }
                    )

        return {
            "operation": step_type,
            "target_files": target_files,
            "reason": str(reason or step.get("reason") or step.get("goal") or "runtime mutation step").strip(),
            "proposed_changes": proposed_changes,
            "metadata": {
                "step_type": step_type,
                "step_id": step.get("id") or step.get("step_id") or "",
                "source": "mutation_runtime_integration",
            },
        }

    # ============================================================
    # lifecycle bridge
    # ============================================================

    def create_preview_for_step(
        self,
        step: Dict[str, Any],
        *,
        reason: str = "",
        created_by: str = "zero",
    ) -> Dict[str, Any]:
        payload = self.build_preview_payload(step, reason=reason)
        if not payload["target_files"]:
            raise MutationBoundaryError("mutation step has no target files")
        return self.boundary.create_preview(
            operation=payload["operation"],
            target_files=payload["target_files"],
            reason=payload["reason"],
            proposed_changes=payload["proposed_changes"],
            metadata=payload["metadata"],
            created_by=created_by,
        )

    def record_after_step(
        self,
        *,
        step: Dict[str, Any],
        step_result: Dict[str, Any],
        verification_result: Optional[Dict[str, Any]] = None,
        replay_result: Optional[Dict[str, Any]] = None,
        approved_by: str = "user",
        actor: str = "zero",
        rollback_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """
        Record a completed guarded mutation step into MutationBoundary.

        The step_result is assumed to be produced by the existing governed
        executor.  This method only records boundary lifecycle state around it.
        """
        if not self.is_mutation_step(step):
            return {
                "ok": True,
                "mutation_recorded": False,
                "reason": "step is not mutation-like",
            }

        step_result = step_result if isinstance(step_result, dict) else {"ok": False, "error": "invalid step_result"}
        payload = self.build_preview_payload(step, step_result=step_result)
        if not payload["target_files"]:
            return {
                "ok": False,
                "mutation_recorded": False,
                "error": "mutation step has no target files",
                "step_type": payload["operation"],
            }

        verify_payload = verification_result if isinstance(verification_result, dict) else {
            "ok": bool(step_result.get("ok")),
            "source": "step_result_default_verification",
        }
        replay_payload = replay_result if isinstance(replay_result, dict) else {
            "ok": bool(verify_payload.get("ok")),
            "source": "step_result_default_replay",
        }

        try:
            final_state = self.boundary.run_governed_mutation_lifecycle(
                operation=payload["operation"],
                target_files=payload["target_files"],
                apply_result=step_result,
                verification_result=verify_payload,
                replay_result=replay_payload,
                reason=payload["reason"],
                proposed_changes=payload["proposed_changes"],
                metadata=payload["metadata"],
                approved_by=approved_by,
                actor=actor,
                rollback_on_failure=rollback_on_failure,
            )
            return {
                "ok": final_state.get("status") in {"verified", "finalized"},
                "mutation_recorded": True,
                "mutation_id": final_state.get("mutation_id", ""),
                "status": final_state.get("status", ""),
                "requires_approval": bool(final_state.get("requires_approval")),
                "risk": copy.deepcopy(final_state.get("risk") or {}),
                "rollback": copy.deepcopy(final_state.get("rollback") or {}),
                "apply": copy.deepcopy(final_state.get("apply") or {}),
                "verification": copy.deepcopy(final_state.get("verification") or {}),
                "final": copy.deepcopy(final_state.get("final") or {}),
            }
        except Exception as exc:
            return {
                "ok": False,
                "mutation_recorded": False,
                "error": str(exc),
                "step_type": payload["operation"],
                "target_files": payload["target_files"],
            }

    # ============================================================
    # formatting
    # ============================================================

    def _truncate_text(self, text: str, limit: int) -> str:
        value = str(text or "")
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 20)] + "...<truncated>"


def create_mutation_runtime_integration(
    workspace_root: str = "workspace",
    project_root: Optional[str] = None,
) -> MutationRuntimeIntegration:
    return MutationRuntimeIntegration(workspace_root=workspace_root, project_root=project_root)


__all__ = [
    "MUTATION_STEP_TYPES",
    "MutationRuntimeIntegration",
    "create_mutation_runtime_integration",
]
