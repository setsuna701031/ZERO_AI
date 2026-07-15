from __future__ import annotations

import json

from cli.zero_agent import build_parser, main


NOW = "2026-07-13T00:00:00Z"


def call(tmp_path, capsys, *args):
    code = main([*args, "--workspace-root", str(tmp_path), "--state-root", str(tmp_path / ".agent"), "--now", NOW, "--json"]); captured = capsys.readouterr(); return code, json.loads(captured.out or captured.err)


def test_reflection_and_memory_cli_json_round_trip(tmp_path, capsys):
    (tmp_path / "README.md").write_text("ZERO", encoding="utf-8")
    _, added = call(tmp_path, capsys, "add", "read README.md"); call(tmp_path, capsys, "run", "--max-missions", "1", "--max-iterations", "10")
    code, reflected = call(tmp_path, capsys, "reflection", added["entry_id"])
    assert code == 0 and reflected["reflection"]["outcome"] == "completed"
    experience_id = reflected["experience"]["experience_id"]
    assert call(tmp_path, capsys, "memory", "list")[1][0]["experience_id"] == experience_id
    assert call(tmp_path, capsys, "memory", "search", "read README.md", "--top-k", "1")[1]["matches"][0]["experience_id"] == experience_id
    assert call(tmp_path, capsys, "memory", "show", experience_id)[1]["experience_id"] == experience_id
    assert call(tmp_path, capsys, "reflection", "rebuild", added["entry_id"])[1]["experience"]["experience_id"] == experience_id


def test_memory_cli_parser_supports_interactive_command_shapes():
    assert build_parser().parse_args(["memory", "list"]).memory_command == "list"
    assert build_parser().parse_args(["memory", "search", "建立 hello.txt"]).text == "建立 hello.txt"
    assert build_parser().parse_args(["reflection", "rebuild", "entry-1"]).entry_id == "entry-1"

