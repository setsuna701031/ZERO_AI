from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core.runtime.runtime_governed_capability_acceptance import run_governed_capability_acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bounded zero-side-effect governed capability runtime acceptance")
    parser.add_argument("input", help="UTF-8 canonical runtime input JSON")
    parser.add_argument("--regression-results", help="UTF-8 JSON results from the separately executed bounded A-G matrix")
    args = parser.parse_args(argv)
    try:
        path = Path(args.input)
        if not path.is_file(): raise ValueError("input_not_regular_file")
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        regressions = None
        if args.regression_results:
            regression_path = Path(args.regression_results)
            if not regression_path.is_file(): raise ValueError("regression_results_not_regular_file")
            regressions = json.loads(regression_path.read_text(encoding="utf-8", errors="strict"))
        result = run_governed_capability_acceptance(value, regressions=regressions)
        code = 0 if result["acceptance_status"] == "accepted" else 1
    except Exception:
        result = {"contract": "zero.runtime.governed_capability_acceptance.v1", "schema_version": "1",
                  "acceptance_status": "blocked", "merge_ready": False, "failure_reasons": ["input_or_acceptance_failed_closed"]}
        code = 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
