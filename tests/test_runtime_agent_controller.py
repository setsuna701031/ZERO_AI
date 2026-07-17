from core.agent.runtime_agent_controller import RuntimeAgentController, load_agent_state
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop
from core.runtime.runtime_event_bus import load_event_bus_state


NOW = "2026-07-13T00:00:00+00:00"


def controller(tmp_path): return RuntimeAgentController(workspace_root=tmp_path, now=NOW)


def run_one(value, entry):
    claimed = value.claim_next(now=NOW); assert claimed["entry_id"] == entry["entry_id"]
    return value.process_entry(entry["entry_id"], now=NOW)


def test_agent_state_is_persisted_and_sealed(tmp_path):
    value = controller(tmp_path); state = load_agent_state(value.agent_state_path)
    assert state["contract"] == "zero.agent.persistent_agent_state.v1" and state["queue_snapshot"] == []


def test_read_only_mission_uses_bootstrap_and_completes(tmp_path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8"); value = controller(tmp_path)
    result = run_one(value, value.add("read README.md", now=NOW))
    assert result["status"] == "completed" and result["mission_id"] and result["mission_session_id"]


def test_mutation_waits_and_approve_reuses_same_session(tmp_path):
    value = controller(tmp_path); entry = value.add("create hello.txt with content hello zero and then verify it", now=NOW)
    waiting = run_one(value, entry); session_id = waiting["mission_session_id"]
    assert waiting["status"] == "waiting_for_approval" and not (tmp_path / "hello.txt").exists()
    completed = value.approve(entry["entry_id"], operator_id="operator", now=NOW)
    assert completed["status"] == "completed" and completed["mission_session_id"] == session_id
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello zero"


def test_denial_blocks_without_mutation(tmp_path):
    value = controller(tmp_path); entry = value.add("create hello.txt with content hello zero", now=NOW); run_one(value, entry)
    denied = value.approve(entry["entry_id"], operator_id="operator", deny=True, reason="not now", now=NOW)
    assert denied["status"] == "blocked" and denied["approval_status"] == "denied" and not (tmp_path / "hello.txt").exists()


def test_pause_resume_stop_are_persisted(tmp_path):
    value = controller(tmp_path)
    assert value.pause(now=NOW)["pause_requested"] is True
    assert value.resume(now=NOW)["agent_status"] == "idle"
    assert value.stop(now=NOW)["stop_requested"] is True


def test_agent_events_include_lifecycle_and_entry_events(tmp_path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8"); value = controller(tmp_path); entry = value.add("read README.md", now=NOW)
    RuntimePersistentAgentLoop(value).run(max_missions=1, max_iterations=2, now=NOW)
    bus = load_event_bus_state(value.event_bus_path); topics = [bus["events"][item]["topic"] for item in bus["event_order"]]
    for topic in ("agent.entry.added", "agent.started", "agent.entry.selected", "agent.entry.completed", "agent.idle"): assert topic in topics

