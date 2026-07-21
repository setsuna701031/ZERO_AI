from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.engineering.engineering_governed_explicit_commit import STORE_FILES as COMMIT_FILES
from core.engineering.engineering_governed_explicit_push import (
    STORE_FILES, authorize_push, build_push_evidence, build_push_preparation, close_push, close_verified_commit,
    execute_push, inspect_push_state, resume_push_state, review_push, verify_remote,
)
from core.engineering.engineering_runtime_session_store import load_session_store, write_session_artifact


def _json(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict): raise ValueError("object_required")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero_engineering_runtime_push",
        description="Governed explicit push orchestration; no stage implies approval, authorization, or execution.")
    parser.add_argument("--store", required=True); parser.add_argument("--session", required=True)
    parser.add_argument("--workspace-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("close-verified-commit")
    prep = sub.add_parser("prepare-push"); prep.add_argument("--remote", required=True); prep.add_argument("--branch", required=True)
    sub.add_parser("verify-remote-before")
    review = sub.add_parser("review-push"); review.add_argument("review_json")
    auth = sub.add_parser("authorize-push"); auth.add_argument("authorization_json")
    execute = sub.add_parser("execute-push"); execute.add_argument("--observed-at", required=True)
    evidence = sub.add_parser("push-evidence"); evidence.add_argument("--observed-at", required=True)
    sub.add_parser("verify-remote-after")
    closure = sub.add_parser("close-push"); closure.add_argument("--closed-at", required=True)
    sub.add_parser("inspect"); sub.add_parser("resume")
    return parser


def main(argv=None) -> int:
    ns = build_parser().parse_args(argv); bundle = load_session_store(ns.store, ns.session)
    command = ns.command
    if command == "close-verified-commit":
        out = close_verified_commit(bundle[COMMIT_FILES["verification"]], bundle[COMMIT_FILES["evidence"]], workspace_root=ns.workspace_root)
        write_session_artifact(ns.store, ns.session, STORE_FILES["verified_commit_closure"], out)
    elif command == "prepare-push":
        out = build_push_preparation(bundle[STORE_FILES["verified_commit_closure"]],
                                     remote=ns.remote, branch=ns.branch, workspace_root=ns.workspace_root)
        write_session_artifact(ns.store, ns.session, STORE_FILES["preparation"], out)
    elif command == "verify-remote-before":
        out = verify_remote(bundle[STORE_FILES["preparation"]], workspace_root=ns.workspace_root)
        write_session_artifact(ns.store, ns.session, STORE_FILES["remote_before"], out)
    elif command == "review-push":
        out = review_push(bundle[STORE_FILES["preparation"]], bundle[STORE_FILES["remote_before"]], _json(ns.review_json))
        write_session_artifact(ns.store, ns.session, STORE_FILES["review"], out)
    elif command == "authorize-push":
        out = authorize_push(bundle[STORE_FILES["preparation"]], bundle[STORE_FILES["remote_before"]],
                             bundle[STORE_FILES["review"]], _json(ns.authorization_json))
        write_session_artifact(ns.store, ns.session, STORE_FILES["authorization"], out)
    elif command == "execute-push":
        used, out = execute_push(bundle[STORE_FILES["preparation"]], bundle[STORE_FILES["remote_before"]],
            bundle[STORE_FILES["review"]], bundle[STORE_FILES["authorization"]],
            bundle[STORE_FILES["verified_commit_closure"]], observed_at=ns.observed_at, workspace_root=ns.workspace_root)
        write_session_artifact(ns.store, ns.session, STORE_FILES["authorization"], used)
        write_session_artifact(ns.store, ns.session, STORE_FILES["execution"], out)
    elif command == "push-evidence":
        out = build_push_evidence(bundle[STORE_FILES["preparation"]], bundle[STORE_FILES["execution"]],
                                  observed_at=ns.observed_at, workspace_root=ns.workspace_root)
        write_session_artifact(ns.store, ns.session, STORE_FILES["evidence"], out)
    elif command == "verify-remote-after":
        prep = bundle[STORE_FILES["preparation"]]
        out = verify_remote(prep, workspace_root=ns.workspace_root, phase="after_push", expected_commit=prep["commit_sha"])
        write_session_artifact(ns.store, ns.session, STORE_FILES["remote_after"], out)
    elif command == "close-push":
        out = close_push(bundle[STORE_FILES["preparation"]], bundle[STORE_FILES["authorization"]],
            bundle[STORE_FILES["execution"]], bundle[STORE_FILES["evidence"]], bundle[STORE_FILES["remote_after"]],
            closed_at=ns.closed_at)
        write_session_artifact(ns.store, ns.session, STORE_FILES["closure"], out)
    elif command == "inspect": out = inspect_push_state(bundle)
    else: out = resume_push_state(bundle)
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
