from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_capability_active_authorization_preparation import (
    prepare_capability_active_authorization,
)
from core.runtime.runtime_capability_active_authorization_preparation_validation import (
    validate_capability_active_authorization_preparation,
)


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser = argparse.ArgumentParser(prog="zero-capability-active-authorization-preparation")
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--prepared-at")
    parser.add_argument("--output")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return {"error": "invalid_arguments"}, int(exc.code)
    try:
        value = json.loads(Path(args.eligibility).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"error": "invalid_json_input"}, 2
    result = prepare_capability_active_authorization(value, prepared_at=args.prepared_at)
    if not validate_capability_active_authorization_preparation(result).valid:
        return {"error": "invalid_preparation"}, 2
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if args.output:
        try:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError:
            return {"error": "output_write_failed"}, 2
    return result, 0 if "invalid_timestamp" not in result["errors"] else 2


def main(argv: list[str] | None = None) -> int:
    value, code = run(argv)
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
