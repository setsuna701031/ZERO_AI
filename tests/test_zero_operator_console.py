from __future__ import annotations

import cli.zero_operator_console as console


def test_transactional_execute_parser_has_only_bounded_arguments():
    parser = console.build_parser()
    command = next(action for action in parser._actions if action.dest == "command")
    transactional = command.choices["transactional-execute"]
    options = set(transactional._option_string_actions)
    assert {"--target-root", "--workspace-root", "--now", "--result-path"} <= options
    assert not {"--force", "--no-rollback", "--skip-validation", "--shell",
                "--git-commit", "--auto-execute"} & options


def test_transactional_execute_delegates_and_preserves_exit_code(monkeypatch, tmp_path, capsys):
    calls = []
    def delegated(*args, **kwargs):
        calls.append((args, kwargs))
        return {"contract": "zero.runtime.transactional_active_execution.v1",
                "transaction_status": "rolled_back"}, 1
    monkeypatch.setattr(console, "run_transactional_execution_cli", delegated)
    code = console.main(["transactional-execute", "a.json", "i.json", "b.json",
        "--target-root", str(tmp_path / "target"), "--workspace-root", str(tmp_path / "work"),
        "--now", "2026-07-10T12:00:00+00:00", "--result-path", str(tmp_path / "result.json")])
    assert code == 1 and len(calls) == 1
    assert calls[0][0] == ("run", "a.json", "i.json", "b.json")
    assert calls[0][1]["target_root"] == str(tmp_path / "target")
    assert '"transaction_status": "rolled_back"' in capsys.readouterr().out

