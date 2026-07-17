from core.agent.runtime_goal_daemon import GoalDaemon, GoalDaemonConfig
from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
from tests.goal_operations_test_support import GOAL_TEXT, NOW, byte_snapshot

def test_two_real_goals_operations_survive_daemon_restart_and_remain_read_only(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); roots = [tmp_path / "site-a", tmp_path / "site-b"]
    for root in roots: root.mkdir()
    goals = [controller.create(f"{GOAL_TEXT} site {index}", target_root=root, now=f"2026-07-13T00:00:0{index}Z") for index, root in enumerate(roots)]
    daemon = GoalDaemon(controller, config=GoalDaemonConfig(max_goals_per_cycle=2, max_missions_started_per_cycle=4), now=NOW); daemon.run_cycle(now=NOW)
    service = GoalOperationsService(GoalOperationsConfig(str(tmp_path), state_root=str(controller.agent_state_root), reference_time=NOW)); before = byte_snapshot(tmp_path)
    overview = service.overview().to_dict(); pending = service.pending_approvals().to_dict()
    assert overview["total_goal_count"] == 2 and pending["pending_approval_count"] == 2
    for goal in goals:
        inspected = service.inspect(goal["goal_id"]).to_dict(); timeline = service.timeline(goal["goal_id"]).to_dict()
        assert inspected["reference_integrity_result"]["integrity"] and "milestone_approved" not in {item["event_category"] for item in timeline["events"]}
    assert service.health().to_dict()["critical"] is False and byte_snapshot(tmp_path) == before
    restarted = RuntimeGoalController(workspace_root=tmp_path, state_root=controller.agent_state_root, now=NOW)
    assert GoalOperationsService(GoalOperationsConfig(str(tmp_path), state_root=str(restarted.agent_state_root))).overview().to_dict()["total_goal_count"] == 2

def test_operations_surface_full_runtime_byte_invariance(tmp_path):
    import hashlib
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); goal = controller.create(GOAL_TEXT, now=NOW); daemon = GoalDaemon(controller, now=NOW)
    for minute in range(20):
        daemon.run_cycle(now=f"2026-07-13T00:{minute:02d}:00Z"); current = controller.show(goal["goal_id"])
        if current["goal_status"] == "waiting_for_approval":
            milestone_id = current["progress"]["waiting_approval_milestones"][0]
            controller.approve(goal["goal_id"], milestone_id, operator_id="byte-invariance-operator", now=f"2026-07-13T00:{minute:02d}:30Z")
        if controller.show(goal["goal_id"])["goal_status"] == "completed": break
    completed = controller.show(goal["goal_id"])
    assert completed["goal_status"] == "completed" and completed["reflection_reference"] and completed["experience_reference"]
    from core.agent.runtime_goal_operations_snapshot import byte_invariance_manifest, load_goal_sources
    config = GoalOperationsConfig(str(tmp_path), state_root=str(controller.agent_state_root), reference_time="2030-01-01T00:00:00Z")
    manifest = byte_invariance_manifest(load_goal_sources(config))
    def hashes():
        result = {}
        for label, roots in manifest.items():
            for index, root in enumerate(roots):
                files = sorted(root.rglob("*")) if root.is_dir() else [root]
                result.update({f"{label}/{index}/{str(path.relative_to(root)).replace(chr(92), '/') if root.is_dir() else path.name}": hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()})
        return result
    before = hashes(); service = GoalOperationsService(config)
    first = service.overview().to_dict(); second = service.overview().to_dict()
    assert first["projection_fingerprint"] == second["projection_fingerprint"] and first["snapshot_identity"] == second["snapshot_identity"]
    service.inspect(goal["goal_id"]); service.timeline(goal["goal_id"]); service.health(); service.pending_approvals()
    after = hashes()
    assert before == after
    names = " ".join(before)
    assert all(token in names for token in ("goal.json", "mission-inbox.json", "goal-daemon.json", "activity-memory.jsonl", "agent-event-bus.json", "execution-approval.json"))
    assert set(first["source_manifest"]) >= set(manifest)
