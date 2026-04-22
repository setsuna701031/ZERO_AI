from __future__ import annotations

import json
import locale
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
WORKSPACE_SHARED = ROOT / "workspace" / "shared"
PYTHON = sys.executable


def run_cmd(*args: str) -> Tuple[int, str, str]:
    process = subprocess.run(
        [PYTHON, str(APP), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=False,
    )

    encoding_candidates = [
        "utf-8",
        locale.getpreferredencoding(False) or "",
        "cp950",
        "cp936",
        "cp1252",
    ]

    def decode_bytes(data: bytes) -> str:
        for enc in encoding_candidates:
            if not enc:
                continue
            try:
                return data.decode(enc)
            except Exception:
                pass
        return data.decode("utf-8", errors="replace")

    stdout = decode_bytes(process.stdout or b"")
    stderr = decode_bytes(process.stderr or b"")
    return process.returncode, stdout, stderr


def print_section(title: str) -> None:
    print("")
    print("=" * 80)
    print(title)
    print("=" * 80)


def extract_first_json_object(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    start = raw.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(raw)):
        ch = raw[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]

    return ""


def parse_json_output(stdout: str, stderr: str = "") -> Dict[str, Any]:
    text = extract_first_json_object(stdout)
    if not text:
        raise AssertionError(
            "no JSON object found in stdout\n"
            f"stdout:\n{stdout}\n\nstderr:\n{stderr}"
        )
    try:
        return json.loads(text)
    except Exception as exc:
        raise AssertionError(f"failed to parse JSON output:\n{text}\n\nstderr:\n{stderr}") from exc


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_contains(text: str, expected: str, message: str) -> None:
    if expected not in text:
        raise AssertionError(f"{message}\nexpected substring: {expected}\nactual text:\n{text}")


def deep_find_value(data: Any, key: str, depth: int = 0) -> Any:
    if depth > 12:
        return None

    if isinstance(data, dict):
        if key in data and data.get(key) not in (None, "", [], {}):
            return data.get(key)
        for value in data.values():
            found = deep_find_value(value, key, depth + 1)
            if found not in (None, "", [], {}):
                return found

    if isinstance(data, list):
        for item in data:
            found = deep_find_value(item, key, depth + 1)
            if found not in (None, "", [], {}):
                return found

    return None


def extract_task_id(create_result: Dict[str, Any]) -> str:
    task = create_result.get("task")
    if isinstance(task, dict):
        task_id = str(task.get("task_id") or task.get("task_name") or "").strip()
        if task_id:
            return task_id

    for key in ("task_id", "task_name"):
        value = str(create_result.get(key) or "").strip()
        if value:
            return value

    raise AssertionError(f"task id missing in create result:\n{json.dumps(create_result, ensure_ascii=False, indent=2)}")


def extract_meta_value(create_result: Dict[str, Any], key: str) -> str:
    value = deep_find_value(create_result, key)
    return str(value).strip() if value not in (None, "", [], {}) else ""


def create_task(goal: str) -> Dict[str, Any]:
    code, stdout, stderr = run_cmd("task", "create", goal)
    assert_true(code == 0, f"task create exited with code {code}\nstderr:\n{stderr}")
    return parse_json_output(stdout, stderr)


def submit_task(task_id: str) -> Dict[str, Any]:
    code, stdout, stderr = run_cmd("task", "submit", task_id)
    assert_true(code == 0, f"task submit exited with code {code}\nstderr:\n{stderr}")
    return parse_json_output(stdout, stderr)


def run_task(task_id: str) -> Dict[str, Any]:
    code, stdout, stderr = run_cmd("task", "run", task_id)
    assert_true(code == 0, f"task run exited with code {code}\nstderr:\n{stderr}")
    return parse_json_output(stdout, stderr)


def task_show(task_id: str) -> str:
    code, stdout, stderr = run_cmd("task", "show", task_id)
    assert_true(code == 0, f"task show exited with code {code}\nstderr:\n{stderr}")
    return stdout


def task_result(task_id: str) -> str:
    code, stdout, stderr = run_cmd("task", "result", task_id)
    assert_true(code == 0, f"task result exited with code {code}\nstderr:\n{stderr}")
    return stdout


def ensure_shared_input() -> None:
    WORKSPACE_SHARED.mkdir(parents=True, exist_ok=True)
    input_path = WORKSPACE_SHARED / "input.txt"
    input_path.write_text(
        "\n".join(
            [
                "Alice will finish API draft by Friday.",
                "Bob will test the upload flow next week.",
                "We need a short summary for the stakeholder meeting.",
                "The team should review and finalize the project document.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    ensure_shared_input()

    print_section("1) command-like goal must be blocked")
    blocked = create_task("python app.py task run task_xxx")
    print(json.dumps(blocked, ensure_ascii=False, indent=2))
    assert_true(blocked.get("ok") is False, "command-like goal should be blocked")
    assert_true(
        str(blocked.get("error_type") or "").strip() == "command_like_goal_blocked",
        "blocked goal should return error_type=command_like_goal_blocked",
    )

    print_section("2) semantic task creation should route to semantic pipelines")
    goals = [
        (
            "summary",
            "summarize input.txt into summary_smoke.txt",
            "semantic_summary_pipeline",
            WORKSPACE_SHARED / "summary_smoke.txt",
        ),
        (
            "action_items",
            "extract action items from input.txt into action_items_smoke.txt",
            "semantic_action_items_pipeline",
            WORKSPACE_SHARED / "action_items_smoke.txt",
        ),
        (
            "report",
            "generate report from input.txt into report_smoke.txt",
            "semantic_report_pipeline",
            WORKSPACE_SHARED / "report_smoke.txt",
        ),
    ]

    created: list[tuple[str, str, Path]] = []

    for semantic_type, goal, expected_route, output_path in goals:
        result = create_task(goal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert_true(result.get("ok") is True, f"{semantic_type} task creation should succeed")

        task_id = extract_task_id(result)
        actual_semantic_type = extract_meta_value(result, "semantic_type")
        actual_route = extract_meta_value(result, "execution_route")

        assert_true(
            actual_semantic_type == semantic_type,
            f"{semantic_type} task should have semantic_type={semantic_type}, got {actual_semantic_type!r}",
        )
        assert_true(
            actual_route == expected_route,
            f"{semantic_type} task should have execution_route={expected_route}, got {actual_route!r}",
        )
        created.append((semantic_type, task_id, output_path))

    print_section("3) submit + targeted task run should finish the requested task and write artifacts")
    for semantic_type, task_id, output_path in created:
        submit_result = submit_task(task_id)
        print(json.dumps(submit_result, ensure_ascii=False, indent=2))
        assert_true(submit_result.get("ok") is True, f"{semantic_type} submit should succeed")

        run_result = run_task(task_id)
        print(json.dumps(run_result, ensure_ascii=False, indent=2))
        assert_true(run_result.get("ok") is True, f"{semantic_type} targeted run should succeed")

        show_text = task_show(task_id)
        print(show_text)
        assert_contains(show_text, "status: finished", f"{semantic_type} task should be finished")
        assert_contains(show_text, "step: 3/3", f"{semantic_type} task should reach 3/3")

        result_text = task_result(task_id)
        print(result_text)
        assert_contains(result_text, "status: finished", f"{semantic_type} result should show finished")

        assert_true(output_path.exists(), f"{semantic_type} output file should exist: {output_path}")
        content = output_path.read_text(encoding="utf-8")
        print(f"[artifact] {output_path}")
        print(content)

        assert_true(content.strip() != "", f"{semantic_type} output should not be empty")
        assert_true("{{previous_result}}" not in content, f"{semantic_type} output should not contain literal placeholder")

    print("")
    print("[semantic-task-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
