from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime


def _failure(code: str) -> dict[str, Any]:
    return {"contract": "zero.runtime.governed_capability_runtime_result.v1", "schema_version": "1",
            "runtime_state": None, "stage_results": {}, "canonical_artifact_bundle": {},
            "prepared_transaction_handoff": None, "transaction_integration_closure": None,
            "runtime_orchestration_closure": None,
            "audit_summary": {"status": "invalid", "reasons": [code], "side_effects_performed": [], "transaction_execute_called": False}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="runs the governed capability pipeline through zero-side-effect transaction preparation; "
                    "does not execute or commit the transaction; does not authorize mutation; "
                    "does not invoke a process, network service, or model; does not persist runtime state")
    parser.add_argument("input", help="UTF-8 JSON governed capability runtime input bundle")
    args = parser.parse_args(argv)
    try:
        path = Path(args.input)
        if not path.is_file():
            result, code = _failure("input_file_not_found_or_not_regular"), 2
        else:
            value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
            result, code = run_governed_capability_runtime(value), 0
    except (OSError, UnicodeError, json.JSONDecodeError):
        result, code = _failure("input_read_or_json_error"), 2
    except Exception:
        result, code = _failure("runtime_failed_closed"), 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
