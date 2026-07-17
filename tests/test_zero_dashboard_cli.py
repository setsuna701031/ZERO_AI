from __future__ import annotations

import json

from cli.zero_dashboard import build_parser, main


def test_cli_contract_and_status_json(tmp_path, capsys):
    args = build_parser().parse_args(["--read-only", "--port", "9000", "--no-browser"])
    assert args.read_only and args.port == 9000 and args.no_browser
    assert main(["--workspace-root", str(tmp_path), "--status", "--json", "--read-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["read_only_mode"] is True
    assert output["server_state"] == "created"


def test_cli_rejects_non_loopback_binding(tmp_path, capsys):
    assert main(["--workspace-root", str(tmp_path), "--host", "0.0.0.0", "--status"]) == 2
    assert "non_loopback_host_rejected" in capsys.readouterr().err
