import json

import pytest

from core.agent.runtime_mission_inbox import (add_mission_entry, cancel_mission_entry, claim_next_mission_entry,
    create_mission_inbox, list_mission_entries, load_mission_inbox, reprioritize_mission_entry,
    runnable_mission_entries, save_mission_inbox, update_mission_entry)


NOW = "2026-07-13T00:00:00+00:00"


def inbox(tmp_path): return create_mission_inbox(workspace_root=tmp_path, state_root=tmp_path.parent / "state", now=NOW)


def test_empty_inbox_round_trip_is_sealed_atomic_utf8(tmp_path):
    path = tmp_path / "state" / "mission-inbox.json"; saved = save_mission_inbox(inbox(tmp_path), path)
    assert load_mission_inbox(path) == saved and json.loads(path.read_text(encoding="utf-8"))["mission_entries"] == {}


def test_chinese_english_deterministic_identity_and_duplicate_input(tmp_path):
    state = inbox(tmp_path)
    state, chinese, created = add_mission_entry(state, "建立 hello.txt，內容是 hello zero", input_id="input-1", now=NOW)
    state, duplicate, created_again = add_mission_entry(state, "different text", input_id="input-1", now=NOW)
    state, english, _ = add_mission_entry(state, "read README.md", input_id="input-2", now=NOW)
    assert created and not created_again and chinese == duplicate
    assert chinese["original_input"].startswith("建立") and english["normalized_input"] == "read README.md"


@pytest.mark.parametrize("priority", ["urgent", "", 123])
def test_priority_validation(tmp_path, priority):
    with pytest.raises(ValueError, match="priority"): add_mission_entry(inbox(tmp_path), "read README.md", priority=priority, now=NOW)


def test_filter_reprioritize_and_cancel_pending(tmp_path):
    state, one, _ = add_mission_entry(inbox(tmp_path), "read README.md", now=NOW)
    state, two, _ = add_mission_entry(state, "read LICENSE", input_id="two", now=NOW)
    state, one = reprioritize_mission_entry(state, one["entry_id"], "high", now=NOW)
    state, two = cancel_mission_entry(state, two["entry_id"], now=NOW)
    assert one["priority"] == "high" and list_mission_entries(state, status="cancelled") == [two]


def test_priority_created_time_tie_break_and_not_before(tmp_path):
    state, low, _ = add_mission_entry(inbox(tmp_path), "read low", priority="low", input_id="low", now="2026-07-13T00:00:00+00:00")
    state, old, _ = add_mission_entry(state, "read old", priority="high", input_id="old", now="2026-07-13T00:00:00+00:00")
    state, future, _ = add_mission_entry(state, "read future", priority="high", input_id="future", not_before="2026-07-14T00:00:00+00:00", now=NOW)
    state, newer, _ = add_mission_entry(state, "read newer", priority="high", input_id="newer", now="2026-07-13T01:00:00+00:00")
    order = [item["entry_id"] for item in runnable_mission_entries(state, now="2026-07-13T02:00:00+00:00")]
    assert future["entry_id"] not in order and order == sorted([old["entry_id"]]) + [newer["entry_id"], low["entry_id"]]


def test_terminal_and_waiting_entries_are_never_selected(tmp_path):
    state = inbox(tmp_path); ids = []
    for index, status in enumerate(("completed", "blocked", "cancelled", "waiting_for_approval")):
        state, entry, _ = add_mission_entry(state, f"read file-{index}", input_id=str(index), now=NOW)
        state, entry = update_mission_entry(state, entry["entry_id"], status=status, now=NOW); ids.append(entry["entry_id"])
    state, selected = claim_next_mission_entry(state, agent_id="agent", now=NOW)
    assert selected is None and not runnable_mission_entries(state, now=NOW)


def test_claim_is_atomic_state_transition_and_not_claimed_twice(tmp_path):
    state, entry, _ = add_mission_entry(inbox(tmp_path), "read README.md", now=NOW)
    state, selected = claim_next_mission_entry(state, agent_id="agent-a", now=NOW)
    state, second = claim_next_mission_entry(state, agent_id="agent-b", now=NOW)
    assert selected["status"] == "selected" and selected["claimed_by"] == "agent-a" and second is None


def test_fingerprint_mismatch_fails_safely(tmp_path):
    path = tmp_path / "inbox.json"; save_mission_inbox(inbox(tmp_path), path)
    raw = json.loads(path.read_text(encoding="utf-8")); raw["updated_at"] = "forged"; path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"): load_mission_inbox(path)

