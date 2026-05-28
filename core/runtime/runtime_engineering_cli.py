from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_engineering_session import RuntimeNativeEngineeringSession
from core.runtime.runtime_native_repo_engineering_surface import RuntimeNativeRepoEngineeringSurface


@dataclass(frozen=True)
class CLIEngineeringCommandResult:
    ok: bool
    command: str
    status: str
    session_id: str = ""
    mutation_id: str = ""
    impacted_files: list[str] = field(default_factory=list)
    test_targets: list[str] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "status": self.status,
            "session_id": self.session_id,
            "mutation_id": self.mutation_id,
            "impacted_files": copy.deepcopy(self.impacted_files),
            "test_targets": copy.deepcopy(self.test_targets),
            "output": copy.deepcopy(self.output),
        }


class CLIEngineeringCommandSurface:
    """
    Codex-like CLI engineering command surface.

    Current supported flow:
      engineering run --goal ...
        -> open persistent engineering session
        -> scan repo / impacted file analysis
        -> create mutation plan
        -> apply controlled mutation
        -> verify
        -> record session timeline
    """

    def __init__(self, *, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root)
        self.repo_surface = RuntimeNativeRepoEngineeringSurface.with_workspace(self.workspace_root)
        self.mutation_loop = RuntimeNativeCodeMutationLoop.with_workspace(self.workspace_root)
        self.session_runtime = RuntimeNativeEngineeringSession.with_workspace(
            self.workspace_root,
            repo_surface=self.repo_surface,
            mutation_loop=self.mutation_loop,
        )

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".") -> "CLIEngineeringCommandSurface":
        return cls(workspace_root=workspace_root)

    def run_goal(
        self,
        *,
        goal: str,
        target_file: str,
        content: str,
        keywords: list[str] | None = None,
        verify_contains: str | None = None,
        max_retries: int = 0,
    ) -> CLIEngineeringCommandResult:
        session = self.session_runtime.open_session(goal=goal)
        captured = self.session_runtime.capture_repo_context(
            session.session_id,
            keywords=keywords or [],
        )

        def plan_fn(goal_text: str, context: dict[str, Any]) -> dict[str, Any]:
            impacted = list(captured.engineering_task.get("impacted_files") or [])
            if target_file not in impacted:
                impacted.insert(0, target_file)
            return {
                "impacted_files": impacted,
                "actions": [
                    {
                        "action_type": "write_file",
                        "target_file": target_file,
                        "content": content,
                    }
                ],
            }

        def verify_fn(record: Any) -> dict[str, Any]:
            target = self.workspace_root / target_file
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            if verify_contains is None:
                ok = target.exists()
            else:
                ok = verify_contains in text
            return {
                "ok": ok,
                "command": f"verify contains {verify_contains!r} in {target_file}",
                "stdout": text,
                "stderr": "" if ok else "verification content not found",
                "returncode": 0 if ok else 1,
            }

        completed = self.session_runtime.run_mutation(
            captured.session_id,
            plan_fn=plan_fn,
            verify_fn=verify_fn,
            max_retries=max_retries,
        )

        mutation_payload = completed.mutation_history[-1] if completed.mutation_history else {}
        mutation_id = str(mutation_payload.get("mutation_id") or "")

        return CLIEngineeringCommandResult(
            ok=completed.status == "completed" and bool(completed.final_result.get("ok")),
            command="engineering run",
            status=completed.status,
            session_id=completed.session_id,
            mutation_id=mutation_id,
            impacted_files=list(captured.engineering_task.get("impacted_files") or []),
            test_targets=list(captured.engineering_task.get("test_targets") or []),
            output={
                "session": completed.to_dict(),
                "summary": self.session_runtime.health(),
            },
        )

    def inspect_session(self, *, session_id: str) -> CLIEngineeringCommandResult:
        session = self.session_runtime.get_session(session_id)
        return CLIEngineeringCommandResult(
            ok=True,
            command="engineering inspect",
            status=session.status,
            session_id=session.session_id,
            impacted_files=list(session.engineering_task.get("impacted_files") or []),
            test_targets=list(session.engineering_task.get("test_targets") or []),
            output={"session": session.to_dict()},
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runtime_engineering_cli")
    parser.add_argument("--workspace", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--goal", required=True)
    run.add_argument("--target-file", required=True)
    run.add_argument("--content", required=True)
    run.add_argument("--keyword", action="append", default=[])
    run.add_argument("--verify-contains", default=None)
    run.add_argument("--max-retries", type=int, default=0)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--session-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    surface = CLIEngineeringCommandSurface.with_workspace(args.workspace)

    if args.command == "run":
        result = surface.run_goal(
            goal=args.goal,
            target_file=args.target_file,
            content=args.content,
            keywords=args.keyword,
            verify_contains=args.verify_contains,
            max_retries=args.max_retries,
        )
    elif args.command == "inspect":
        result = surface.inspect_session(session_id=args.session_id)
    else:
        parser.error(f"unsupported command: {args.command}")
        return 2

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
