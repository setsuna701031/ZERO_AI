from __future__ import annotations

import json

import pytest

from cli.zero_agent import main
from core.agent.runtime_agent_controller import RuntimeAgentController, default_agent_state_root


NOW = "2026-07-13T00:00:00Z"


def test_add_creates_missing_nested_workspace_and_complete_agent_state(tmp_path, capsys):
    workspace = tmp_path / "workspace" / "agent-test"
    code = main(["add", "create agent_test.txt with content zero agent", "--workspace-root", str(workspace), "--now", NOW, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["status"] == "pending"
    assert workspace.is_dir()
    state_root = default_agent_state_root(workspace)
    assert (state_root / "mission-inbox.json").is_file()
    assert (state_root / "agent-state.json").is_file()
    assert (state_root / "agent-event-bus.json").is_file()


def test_controller_workspace_bootstrap_is_idempotent_and_state_root_deterministic(tmp_path):
    workspace = tmp_path / "one" / "two"
    first = RuntimeAgentController(workspace_root=workspace, now=NOW)
    second = RuntimeAgentController(workspace_root=workspace, now=NOW)
    assert first.workspace_root == workspace.resolve()
    assert first.state_root == second.state_root == default_agent_state_root(workspace)
    assert first.load_state()["agent_id"] == second.load_state()["agent_id"]


def test_non_add_commands_do_not_create_missing_workspace(tmp_path, capsys):
    workspace = tmp_path / "absent"
    code = main(["list", "--workspace-root", str(workspace), "--json"])
    error = json.loads(capsys.readouterr().err)
    assert code == 2 and error["error"] == "workspace_root_not_found"
    assert not workspace.exists()


def test_workspace_file_and_relative_traversal_are_rejected(tmp_path, monkeypatch):
    file_root = tmp_path / "not-a-directory"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace_root_not_directory"):
        RuntimeAgentController(workspace_root=file_root)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="unsafe_workspace_path_traversal"):
        RuntimeAgentController(workspace_root="..\\outside")

