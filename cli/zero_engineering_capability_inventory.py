from __future__ import annotations

import argparse
import json
import sys

from core.engineering.engineering_repository_capability_inventory import build_repository_capability_inventory, inspect_repository_capability_inventory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inventory", "integration-map", "gaps", "inspect"))
    parser.add_argument("--repository-root", required=True)
    return parser


def run(argv=None):
    try: args = build_parser().parse_args(argv)
    except SystemExit as exc: return {"error": "argument_error"}, int(exc.code or 2)
    value = build_repository_capability_inventory(args.repository_root)
    if args.mode == "integration-map": output = {"integration_map": value["integration_map"]}
    elif args.mode == "gaps": output = {"gap_findings": value["gap_findings"], "duplicate_candidate_findings": value["duplicate_candidate_findings"]}
    elif args.mode == "inspect": output = inspect_repository_capability_inventory(value)
    else: output = value
    return output, 0 if value["status"] == "inventoried" else 1


def main(argv=None):
    value, code = run(argv)
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    return code


if __name__ == "__main__": raise SystemExit(main())
