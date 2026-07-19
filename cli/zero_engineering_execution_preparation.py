from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.engineering.engineering_execution_eligibility import build_engineering_execution_eligibility
from core.engineering.engineering_execution_environment_requirements import build_engineering_execution_environment_requirements
from core.engineering.engineering_execution_preconditions import build_engineering_execution_preconditions
from core.engineering.engineering_execution_preparation_closure import build_engineering_execution_preparation_closure
from core.engineering.engineering_execution_preparation_intake import build_engineering_execution_preparation_intake
from core.engineering.engineering_execution_resource_plan import build_engineering_execution_resource_plan
from core.engineering.engineering_execution_validation import validate_engineering_execution_preparation


STAGES = ("intake", "eligibility", "preconditions", "environment_requirements", "resource_plan", "validation", "closure")


def _read(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def build_pipeline(authorization_closure, intent):
    intake = build_engineering_execution_preparation_intake(authorization_closure, intent)
    eligibility = build_engineering_execution_eligibility(intake, intent)
    preconditions = build_engineering_execution_preconditions(intake, eligibility, intent)
    environment = build_engineering_execution_environment_requirements(preconditions, intent)
    resources = build_engineering_execution_resource_plan(environment, intent)
    validation = validate_engineering_execution_preparation(intake, eligibility, preconditions, environment, resources)
    closure = build_engineering_execution_preparation_closure(intake, eligibility, preconditions, environment, resources, validation)
    return {
        "intake": intake,
        "eligibility": eligibility,
        "preconditions": preconditions,
        "environment_requirements": environment,
        "resource_plan": resources,
        "validation": validation,
        "closure": closure,
    }


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("engineering_authorization_closure_json")
    parser.add_argument("--intent")
    parser.add_argument("--stage", choices=STAGES, default="closure")
    return parser


def run(argv=None):
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as error:
        return {"error": "argument_error"}, int(error.code or 2)
    try:
        artifacts = build_pipeline(
            _read(arguments.engineering_authorization_closure_json),
            _read(arguments.intent) if arguments.intent else {},
        )
        return artifacts[arguments.stage], 0 if artifacts["validation"]["status"] == "validated" else 1
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"error": "input_error"}, 2


def main(argv=None):
    value, code = run(argv)
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["STAGES", "build_parser", "build_pipeline", "main", "run"]
