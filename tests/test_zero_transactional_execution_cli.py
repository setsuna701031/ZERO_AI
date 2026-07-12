from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import cli.zero_transactional_execution as cli
import core.runtime.runtime_transactional_active_execution as runtime
from tests.test_runtime_transactional_active_execution import NOW, candidate, records


def write(path: Path, value: dict, *, bom: bool = False) -> None:
    path.write_text(json.dumps(value), encoding="utf-8-sig" if bom else "utf-8")


def files(tmp_path, *, invalid=None, bom=False):
    values = records(tmp_path, [candidate("a.txt", "create", content="a")])
    paths = [tmp_path / name for name in ("auth.json", "request.json", "bundle.json")]
    for index, (path, value) in enumerate(zip(paths, values[:3])):
        if invalid == index:
            path.write_text("bad json")
        else:
            write(path, value, bom=bom)
    return values, paths


def test_committed_exit_zero_bom_result_path_status_and_input_purity(tmp_path):
    values, paths = files(tmp_path, bom=True)
    before = [path.read_bytes() for path in paths]
    result_path = tmp_path / "results" / "transaction.json"
    result, code = cli.run_transactional_execution_cli(
        "run", *paths, target_root=values[3], workspace_root=values[4],
        now=NOW, result_path=result_path)
    assert code == 0 and result["transaction_status"] == "committed"
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
    assert [path.read_bytes() for path in paths] == before
    status, code = cli.run_transactional_execution_cli("status", result_path,
        result_path=result_path)
    assert code == 0 and status["transaction_status"] == "committed"


def test_blocked_and_workspace_inside_target_exit_one(tmp_path):
    values, paths = files(tmp_path)
    values[0]["authorization_status"] = "invalid"; write(paths[0], values[0])
    result, code = cli.run_transactional_execution_cli("run", *paths,
        target_root=values[3], workspace_root=values[4], now=NOW,
        result_path=tmp_path / "blocked.json")
    assert code == 1 and result["transaction_status"] == "blocked"
    values, paths = files(tmp_path / "inside")
    result, code = cli.run_transactional_execution_cli("run", *paths,
        target_root=values[3], workspace_root=values[3] / "workspace", now=NOW,
        result_path=tmp_path / "inside-result.json")
    assert code == 1 and result["transaction_status"] == "blocked"


def test_rolled_back_exit_one(tmp_path):
    values = records(tmp_path, [candidate("a.py", "replace", before="x=1\n", content="def broken(:")],
                     profile="python_compile", project_validation_required=True)
    (values[3] / "a.py").write_bytes(b"x=1\n")
    paths = [tmp_path / name for name in ("a.json", "r.json", "b.json")]
    for path, value in zip(paths, values[:3]): write(path, value)
    result, code = cli.run_transactional_execution_cli("run", *paths,
        target_root=values[3], workspace_root=values[4], now=NOW,
        result_path=tmp_path / "rolled.json")
    assert code == 1 and result["transaction_status"] == "rolled_back"
    status, code = cli.run_transactional_execution_cli("status", tmp_path / "rolled.json",
        result_path=tmp_path / "rolled.json")
    assert code == 0 and status["transaction_status"] == "rolled_back"


@pytest.mark.parametrize("invalid", [0, 1, 2])
def test_each_invalid_json_input_returns_two(tmp_path, invalid):
    values, paths = files(tmp_path, invalid=invalid)
    result, code = cli.run_transactional_execution_cli("run", *paths,
        target_root=values[3], workspace_root=values[4], now=NOW,
        result_path=tmp_path / "error.json")
    assert code == 2 and result["transaction_status"] == "input_error"


@pytest.mark.parametrize("status", ["blocked", "rolled_back", "rollback_failed"])
def test_status_reads_all_legal_results(tmp_path, status):
    path = tmp_path / "result.json"
    write(path, {"contract": cli.CONTRACT, "transaction_status": status})
    result, code = cli.run_transactional_execution_cli("status", path, result_path=path)
    assert code == 0 and result["transaction_status"] == status


def test_invalid_status_result_returns_two(tmp_path):
    path = tmp_path / "bad.json"; write(path, {"contract": "wrong"})
    result, code = cli.run_transactional_execution_cli("status", path, result_path=path)
    assert code == 2 and result["transaction_status"] == "input_error"


def test_parser_exposes_no_force_shell_or_rollback_bypass_flags():
    parser = cli.build_parser()
    run_parser = next(action for action in parser._actions if action.dest == "command").choices["run"]
    options = set(run_parser._option_string_actions)
    assert not {"--shell", "--skip-validation", "--no-rollback", "--force",
                "--auto-approve", "--pytest-args"} & options


def test_usage_errors_raise_argparse_exit_two():
    with pytest.raises(SystemExit) as missing:
        cli.main(["run"])
    assert missing.value.code == 2


def test_cli_maps_rollback_failed_to_exit_three(monkeypatch, tmp_path):
    values = records(tmp_path, [candidate("a.py", "replace", before="x=1\n", content="def broken(:")],
                     profile="python_compile", project_validation_required=True)
    (values[3] / "a.py").write_bytes(b"x=1\n")
    paths = [tmp_path / name for name in ("a.json", "r.json", "b.json")]
    for path, value in zip(paths, values[:3]):
        write(path, value)
    original = runtime._atomic_write
    def fail_rollback(path, data, *, suffix):
        if "rollback" in suffix:
            raise OSError("injected rollback failure")
        return original(path, data, suffix=suffix)
    monkeypatch.setattr(runtime, "_atomic_write", fail_rollback)
    result, code = cli.run_transactional_execution_cli("run", *paths,
        target_root=values[3], workspace_root=values[4], now=NOW,
        result_path=tmp_path / "critical.json")
    assert code == 3 and result["transaction_status"] == "rollback_failed"
