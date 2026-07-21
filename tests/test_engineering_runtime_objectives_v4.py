import json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_runtime_session_v3 import *
from core.engineering.engineering_runtime_objectives_v4 import *


def repo(): return {"repository_id":"repo","repository_fingerprint":"rfp"}
def task(): return {"task_id":"task"}
def ref(name="ev", schema="zero.engineering.verification_evidence.v1", session_id=None):
    r={"schema":schema,"artifact_identity":name,"artifact_fingerprint":"f"+name}
    if session_id: r["session_id"]=session_id
    return r

def sess(name="task"): return create_engineering_runtime_session(repo(), {"task_id":name})
def cycle(s,n,prev=None,status="closed"):
    return build_engineering_runtime_cycle(session_id=s["session_id"],cycle_number=n,previous_cycle=prev,proposal_reference=ref(f"p{n}"),cycle_status=status)
def obj(s, oid="one", required=True, scope=("core/engineering",), status="defined", evs=()):
    return build_session_objective(s,source_task_identity=task(),source_planning_reference=None,objective_statement=f"do {oid}",bounded_scope=scope,priority=("required" if required else "optional"),acceptance_criteria=[{"criterion_id":"c1","description":"crit1","required":required,"evidence_type":"test","verification_method":"pytest","status":status,"evidence_references":list(evs)}],required_evidence=[])
def assignment(s,c,o): return build_cycle_objective_assignment(s,c,[o],target_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}],declared_scope=o["bounded_scope"],excluded_scope=[],expected_evidence=[])
def progress(s,o,a,**kw): return evaluate_objective_progress(s,[o],a,**kw)

# 10.1 Objective Contract

def test_deterministic_objective_creation_stable_identity_and_fingerprint():
    s=sess(); a=obj(s); b=obj(s); assert a==b and a["objective_id"] and a["objective_fingerprint"]
def test_empty_objective_rejection():
    s=sess(); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="", bounded_scope=["x"], acceptance_criteria=[{"criterion_id":"c"}], required_evidence=[])
def test_missing_acceptance_criteria_rejection():
    s=sess(); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="x", bounded_scope=["x"], acceptance_criteria=[], required_evidence=[])
def test_duplicate_criterion_rejection():
    s=sess(); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="x", bounded_scope=["x"], acceptance_criteria=[{"criterion_id":"c"},{"criterion_id":"c"}], required_evidence=[])
def test_invalid_criterion_status_rejection():
    s=sess(); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="x", bounded_scope=["x"], acceptance_criteria=[{"criterion_id":"c","status":"done"}], required_evidence=[])
def test_child_scope_expansion_rejection():
    s=sess(); p=obj(s,scope=["a"]); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="x", bounded_scope=["b"], acceptance_criteria=[{"criterion_id":"c"}], required_evidence=[], parent_objective=p)
def test_fake_artifact_reference_rejection():
    s=sess(); pytest.raises(RuntimeSessionError, build_session_objective, s, source_task_identity=task(), source_planning_reference=None, objective_statement="x", bounded_scope=["x"], acceptance_criteria=[{"criterion_id":"c","evidence_references":[ref("bad","zero.test.fake.v1")]}], required_evidence=[])

# 10.2 Cycle Assignment

def test_cycle_1_objective_assignment():
    s=sess(); c=cycle(s,1); o=obj(s); assert assignment(s,c,o)["cycle_number"]==1
def test_cycle_2_remaining_objective_assignment():
    s=sess(); c1=cycle(s,1); s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); o=obj(s); assert assignment(s,c2,o)["cycle_number"]==2
def test_cycle_3_remaining_objective_assignment():
    s=sess(); c1=cycle(s,1); s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); s=append_engineering_runtime_cycle(s,c2); c3=cycle(s,3,c2); assert assignment(s,c3,obj(s))["cycle_number"]==3
def test_mixed_session_objective_rejection():
    s=sess(); other=sess("other"); c=cycle(s,1); pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c,[obj(other)],target_criteria=[],declared_scope=["core/engineering"],excluded_scope=[],expected_evidence=[])
def test_unknown_objective_rejection():
    s=sess(); c=cycle(s,1); o=obj(s); pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c,[o],target_criteria=[{"objective_id":"missing","criterion_id":"c1"}],declared_scope=o["bounded_scope"],excluded_scope=[],expected_evidence=[])
def test_unknown_criterion_rejection():
    s=sess(); c=cycle(s,1); o=obj(s); pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c,[o],target_criteria=[{"objective_id":o["objective_id"],"criterion_id":"missing"}],declared_scope=o["bounded_scope"],excluded_scope=[],expected_evidence=[])
def test_scope_expansion_rejection():
    s=sess(); c=cycle(s,1); o=obj(s,scope=["a"]); pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c,[o],target_criteria=[],declared_scope=["b"],excluded_scope=[],expected_evidence=[])
def test_duplicate_assignment_rejection():
    s=sess(); c=cycle(s,1); o=obj(s); t={"objective_id":o["objective_id"],"criterion_id":"c1"}; pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c,[o],target_criteria=[t,t],declared_scope=o["bounded_scope"],excluded_scope=[],expected_evidence=[])
def test_terminal_session_assignment_rejection():
    s=sess(); c1=cycle(s,1); s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); s=append_engineering_runtime_cycle(s,c2); c3=cycle(s,3,c2); s=close_engineering_runtime_session(complete_session(append_engineering_runtime_cycle(s,c3))); pytest.raises(RuntimeSessionError, build_cycle_objective_assignment, s,c3,[obj(s)],target_criteria=[],declared_scope=["core/engineering"],excluded_scope=[],expected_evidence=[])

# 10.3 Progress Evaluation

def test_criterion_satisfied_with_valid_evidence():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a,satisfied_evidence=[ref("e",session_id=s["session_id"])]); assert p["criteria_results"][0]["status"]=="satisfied"
def test_missing_evidence_not_satisfied():
    s=sess(); o=obj(s); p=progress(s,o,assignment(s,cycle(s,1),o)); assert p["criteria_results"][0]["status"]=="not_satisfied"
def test_execution_completed_but_criterion_not_satisfied(): test_missing_evidence_not_satisfied()
def test_verification_passed_but_unrelated_criterion_not_satisfied(): test_missing_evidence_not_satisfied()
def test_partial_satisfaction():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); assert progress(s,o,a,partial_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}])["criteria_results"][0]["status"]=="partially_satisfied"
def test_blocked_criterion():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); assert progress(s,o,a,blocked_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}])["progress_status"]=="blocked"
def test_failed_criterion():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); assert progress(s,o,a,failed_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}])["progress_status"]=="failed"
def test_unsupported_completion_claim():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a,satisfied_evidence=[ref("e",session_id=s["session_id"])],blocked_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}]); assert p["unsupported_claims"]
def test_scope_deviation():
    s=sess(); o=obj(s,scope=["a"]); a=assignment(s,cycle(s,1),o); assert progress(s,o,a,satisfied_evidence=[ref("e",session_id=s["session_id"])],scope_observations=["b"])["scope_deviation"]
def test_feedback_unresolved_issue_prevents_satisfaction():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a,satisfied_evidence=[ref("e",session_id=s["session_id"])],feedback={"unresolved_criteria":[o["objective_id"]+":c1"]}); assert p["criteria_results"][0]["status"]=="blocked"

# 10.4/10.5 Completion

def test_all_required_criteria_satisfied_and_candidate_is_not_completed():
    s=sess(); o=obj(s); p=progress(s,o,assignment(s,cycle(s,1),o),satisfied_evidence=[ref("e",session_id=s["session_id"])]); r=evaluate_completion_readiness(s,[o],[p]); assert r["completion_candidate"] and not r["session_completed"]
def test_optional_criterion_incomplete_does_not_necessarily_block():
    s=sess(); o=obj(s, required=False); r=evaluate_completion_readiness(s,[o],[]); assert r["required_objective_count"]==0
def test_required_criterion_incomplete_blocks_missing_evidence_invalid_lineage_scope_failed_cycle_unresolved_feedback():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a,feedback={"unresolved_criteria":[o["objective_id"]+":c1"]},scope_observations=["outside"]); r=evaluate_completion_readiness(s,[o],[p],[{"cycle_status":"failed"}]); assert not r["completion_candidate"] and {"missing_evidence","scope_deviation","failed_cycle","unresolved_feedback"}.issubset(set(r["completion_blockers"]))
def test_review_request_contains_no_authority_and_does_not_close_session():
    s=sess(); o=obj(s); p=progress(s,o,assignment(s,cycle(s,1),o),satisfied_evidence=[ref("e",session_id=s["session_id"])]); rr=request_completion_review(s,evaluate_completion_readiness(s,[o],[p])); assert rr["authority_state"]=="not_granted" and not rr["session_completed"]
def test_missing_human_actor_rejected_invalid_decision_rejected():
    s=sess(); rr={"schema":REVIEW_REQUEST_SCHEMA,"review_request_id":"r","review_request_fingerprint":"f","session_id":s["session_id"]}; pytest.raises(RuntimeSessionError, record_completion_decision, s, rr, decision="approved_complete", human_actor_reference={}); pytest.raises(RuntimeSessionError, record_completion_decision, s, rr, decision="yes", human_actor_reference={"actor_id":"h"})
def test_approved_complete_permits_completed_transition_returned_rejected_do_not_complete_or_create_cycle_and_not_approval():
    s=sess(); c1=cycle(s,1); s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); s=append_engineering_runtime_cycle(s,c2); c3=cycle(s,3,c2); s=append_engineering_runtime_cycle(s,c3); rr={"schema":REVIEW_REQUEST_SCHEMA,"review_request_id":"r","review_request_fingerprint":"f","session_id":s["session_id"]}; d=record_completion_decision(s,rr,decision="approved_complete",human_actor_reference={"actor_id":"h"}); assert d["permits_completed_transition"] and d["not_proposal_approval"] and apply_completion_decision(s,d)["status"]=="completed"; assert not record_completion_decision(s,rr,decision="returned_for_iteration",human_actor_reference={"actor_id":"h"})["permits_completed_transition"]; assert not record_completion_decision(s,rr,decision="rejected_incomplete",human_actor_reference={"actor_id":"h"})["permits_completed_transition"]
def test_closed_session_cannot_receive_new_completion_decision():
    s=sess(); c1=cycle(s,1); s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); s=append_engineering_runtime_cycle(s,c2); c3=cycle(s,3,c2); s=close_engineering_runtime_session(complete_session(append_engineering_runtime_cycle(s,c3))); pytest.raises(RuntimeSessionError, record_completion_decision, s, {"schema":REVIEW_REQUEST_SCHEMA,"review_request_id":"r","review_request_fingerprint":"f"}, decision="approved_complete", human_actor_reference={"actor_id":"h"})

# 10.6/10.7 health and next candidate

def test_iteration_health_progressing_slow_stalled_repeating_failure_and_threshold():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p1=progress(s,o,a,satisfied_evidence=[ref("e1",session_id=s["session_id"])]); assert evaluate_iteration_health(s,[p1])["health_status"]=="progressing"; p2=progress(s,o,a,satisfied_evidence=[ref("e2",session_id=s["session_id"])],blocked_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}]); assert evaluate_iteration_health(s,[p2])["health_status"]=="slow_progress"; p0=progress(s,o,a,verification_failures=[{"finding_id":"f"}]); h=evaluate_iteration_health(s,[p0,p0,p0]); assert h["health_status"]=="repeating_failure" and h["recommended_action"]=="human_reassessment_required" and h["bounded_no_progress_threshold"]==3 and h["repeated_gap_references"]
def test_multiple_cycles_no_progress_stalled_no_unbounded_continuation():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a); h=evaluate_iteration_health(s,[p,p,p]); assert h["stalled_cycle_count"]==3 and h["recommended_action"]=="human_reassessment_required"
def test_next_objective_candidate_uses_remaining_bounded_and_not_proposal_authorized_executable():
    s=sess(); o=obj(s); p=progress(s,o,assignment(s,cycle(s,1),o)); c=create_next_iteration_objective_candidate(s,p,[o]); assert c["candidate_only"] and c["not_a_proposal"] and c["not_approved"] and c["not_authorized"] and c["not_executable"] and c["bounded_scope"]==o["bounded_scope"]
def test_candidate_cannot_add_unknown_objective_or_expand_scope_and_blocked_when_stalled():
    s=sess(); o=obj(s); p=progress(s,o,assignment(s,cycle(s,1),o)); bad=dict(p); bad["remaining_criteria"]=[{"objective_id":"unknown","criterion_id":"c1"}]; pytest.raises(RuntimeSessionError, create_next_iteration_objective_candidate, s,bad,[o]); pytest.raises(RuntimeSessionError, create_next_iteration_objective_candidate, s,p,[o],health={"recommended_action":"human_reassessment_required"})

# 10.8/10.9 integration, persistence, CLI

def test_three_cycle_complete_case_and_closed_session_cannot_append_cycle_4():
    s=sess(); o=obj(s); c1=cycle(s,1); a1=assignment(s,c1,o); p1=progress(s,o,a1,partial_criteria=[{"objective_id":o["objective_id"],"criterion_id":"c1"}]); assert not evaluate_completion_readiness(s,[o],[p1])["completion_candidate"]; s=append_engineering_runtime_cycle(s,c1); c2=cycle(s,2,c1); p2=progress(s,o,assignment(s,c2,o)); assert not evaluate_completion_readiness(s,[o],[p1,p2])["completion_candidate"]; s=append_engineering_runtime_cycle(s,c2); c3=cycle(s,3,c2); p3=progress(s,o,assignment(s,c3,o),satisfied_evidence=[ref("e",session_id=s["session_id"])]); s=append_engineering_runtime_cycle(s,c3); r=evaluate_completion_readiness(s,[o],[p1,p2,p3]); assert r["completion_candidate"] and s["status"]!="completed"; rr=request_completion_review(s,r); d=record_completion_decision(s,rr,decision="approved_complete",human_actor_reference={"actor_id":"human"}); closed=close_engineering_runtime_session(apply_completion_decision(s,d)); assert closed["status"]=="closed"; pytest.raises(RuntimeSessionError, append_engineering_runtime_cycle, closed, cycle(closed,4,c3))
def test_ineffective_loop_case_has_no_auto_cycle_or_proposal():
    s=sess(); o=obj(s); a=assignment(s,cycle(s,1),o); p=progress(s,o,a,verification_failures=[{"finding_id":"f"}]); h=evaluate_iteration_health(s,[p,p,p]); dec=decide_iteration(s,p,evaluate_completion_readiness(s,[o],[p,p,p]),h); assert dec["decision"]=="human_reassessment_required" and dec["next_objective_candidates"]==[]
def test_resume_inspect_journal_checkpoint_and_corruption(tmp_path):
    s=sess(); store=RuntimeSessionStore(tmp_path); store.create(s); o=obj(s); store.save_objective(o); c=cycle(s,1); store.save_cycle(c); a=assignment(s,c,o); store.save_assignment(a); p=progress(s,o,a); store.save_progress(p); h=evaluate_iteration_health(s,[p]); store.save_iteration_health(h); cp=build_checkpoint({**s,"v3_4_objective_coordination":{"objective_count":1,"required_objective_count":1,"remaining_objective_count":1,"iteration_health":h["health_status"],"completion_readiness":"continue_iteration","resume_decision":"requires_objective_evaluation"}},[c],[]); store.save_checkpoint(cp); before=sorted(x.read_text() for x in tmp_path.rglob("*.json")); ins=inspect_engineering_runtime_session(s,[c],cp); after=sorted(x.read_text() for x in tmp_path.rglob("*.json")); assert before==after and ins["objective_count"]==1 and resume_decision(s,[c],cp)["decision"]=="requires_objective_evaluation"; e=make_journal_entry(s["session_id"],1,"session_objective_defined",None,{"schema":o["schema"],"artifact_identity":o["objective_id"],"artifact_fingerprint":o["objective_fingerprint"]},None,s["status"]); assert replay_journal([e],s["session_id"])["events"]==["session_objective_defined"]; (tmp_path/s["session_id"]/"objectives"/f"{o['objective_id']}.json").write_text(json.dumps({**o,"objective_fingerprint":"bad"},sort_keys=True,separators=(",",":"))+"\n"); pytest.raises(RuntimeSessionError, validate_session_objective, RuntimeSessionStore(tmp_path).load(s["session_id"])["objectives"][0], s); pytest.raises(RuntimeSessionError, store._base, "../bad")
def test_cli_json_stdout_parseable_and_invalid_decision_exit_code(tmp_path):
    ri=tmp_path/'ri.json'; ti=tmp_path/'ti.json'; ri.write_text(json.dumps(repo())); ti.write_text(json.dumps(task())); store=tmp_path/'store'; out=subprocess.run([sys.executable,'-m','cli.zero_engineering_runtime_session','create','--repository-identity',str(ri),'--task-identity',str(ti),'--store',str(store)],text=True,capture_output=True); s=json.loads(out.stdout); assert out.returncode==0
    inp=tmp_path/'obj.json'; inp.write_text(json.dumps({"objectives":[{"objective_statement":"do","bounded_scope":["core/engineering"],"acceptance_criteria":[{"criterion_id":"c1"}]}]})); assert subprocess.run([sys.executable,'-m','cli.zero_engineering_runtime_session','define-objectives','--store',str(store),'--session-id',s['session_id'],'--input',str(inp)],text=True,capture_output=True).returncode==0
    cf=tmp_path/'c.json'; c=cycle(s,1); cf.write_text(json.dumps(c)); assert subprocess.run([sys.executable,'-m','cli.zero_engineering_runtime_session','append-cycle','--store',str(store),'--session-id',s['session_id'],'--cycle',str(cf)],text=True,capture_output=True).returncode==0
    ain=tmp_path/'a.json'; ain.write_text(json.dumps({"target_criteria":[{"objective_id":RuntimeSessionStore(store).load(s['session_id'])['objectives'][0]['objective_id'],"criterion_id":"c1"}],"declared_scope":["core/engineering"]})); assert subprocess.run([sys.executable,'-m','cli.zero_engineering_runtime_session','assign-cycle-objectives','--store',str(store),'--session-id',s['session_id'],'--cycle-number','1','--input',str(ain)],text=True,capture_output=True).returncode==0
    pin=tmp_path/'p.json'; pin.write_text(json.dumps({}));
    for cmd in ['evaluate-progress','evaluate-completion','evaluate-iteration-health','inspect','resume']:
        args=[sys.executable,'-m','cli.zero_engineering_runtime_session',cmd,'--store',str(store),'--session-id',s['session_id']]
        if cmd=='evaluate-progress': args += ['--cycle-number','1','--input',str(pin)]
        r=subprocess.run(args,text=True,capture_output=True); assert r.returncode==0; json.loads(r.stdout)
    r=subprocess.run([sys.executable,'-m','cli.zero_engineering_runtime_session','record-completion-decision','--store',str(store),'--session-id',s['session_id'],'--review-request',str(ri),'--decision','bad','--human-actor','{"actor_id":"h"}'],text=True,capture_output=True); assert r.returncode!=0
