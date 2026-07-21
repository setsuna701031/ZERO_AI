import json, subprocess, sys
import pytest
from core.engineering.engineering_runtime_session_v3 import *

def ref(kind,i): return {"schema":f"zero.engineering.{kind}.v1","artifact_identity":f"{kind}-{i}","artifact_fingerprint":f"fp-{kind}-{i}"}
def repo(): return {"repository_id":"repo-zero","repository_fingerprint":"repo-fp"}
def task(): return {"task_id":"task-zero"}
def mk_session(): return create_engineering_runtime_session(repo(),task())
def mk_cycle(s,n,prev=None,full=False,closed=False):
    kw={"session_id":s["session_id"],"cycle_number":n,"previous_cycle":prev,"proposal_reference":ref("proposal",n)}
    if full or closed:
        kw.update(approval_reference=ref("approval",n),authorization_reference=ref("authorization",n),execution_session_reference=ref("execution_session",n),execution_result_reference=ref("execution_result",n),verification_runtime_reference=ref("verification_runtime",n),verification_result_reference=ref("verification_result",n),feedback_reference=ref("feedback",n),cycle_status="closed" if closed else None,cycle_closure_reference=ref("cycle_closure",n) if closed else None)
    return build_engineering_runtime_cycle(**kw)

def test_session_create_deterministic_and_rejects_bad_repo():
    a=mk_session(); b=mk_session(); assert a==b; assert a["status"]=="created"; assert a["cycle_count"]==0; validate_engineering_runtime_session(a)
    with pytest.raises(RuntimeSessionError): create_engineering_runtime_session({"repository_id":"x"},task())

def test_three_cycle_continuity_and_closed_append_rejected():
    s=mk_session(); c1=mk_cycle(s,1,closed=True); s=append_engineering_runtime_cycle(s,c1)
    c2=mk_cycle(s,2,c1,closed=True); s=append_engineering_runtime_cycle(s,c2)
    c3=mk_cycle(s,3,c2,closed=True); s=append_engineering_runtime_cycle(s,c3)
    assert len({c1["cycle_id"],c2["cycle_id"],c3["cycle_id"]})==3
    s=complete_session(s); assert s["status"]=="completed"; s=close_engineering_runtime_session(s); assert s["status"]=="closed"
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s,mk_cycle(s,4,c3))

def test_cycle_negative_linkage_cases():
    s=mk_session(); c1=mk_cycle(s,1); s1=append_engineering_runtime_cycle(s,c1)
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,mk_cycle(s1,3,c1))
    bad=mk_cycle(s1,2,c1); bad={**bad,"previous_cycle_fingerprint":"wrong"};
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,bad)
    other=create_engineering_runtime_session(repo(),{"task_id":"other-task"});
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,mk_cycle(other,2,c1))
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,c1)

def test_governance_no_inherited_approval_authorization_and_candidates_not_executable():
    s=mk_session(); c1=mk_cycle(s,1,closed=True); s=append_engineering_runtime_cycle(s,c1)
    c2=build_engineering_runtime_cycle(session_id=s["session_id"],cycle_number=2,previous_cycle=c1,proposal_reference=ref("proposal",2),approval_reference=c1["approval_reference"],authorization_reference=ref("authorization",2))
    with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s,c2)
    cand=build_proposal_candidate(s,c1,ref("verification_result",1),ref("feedback",1),objective="improve bounded check",bounded_scope=["core/engineering"])
    assert cand["candidate_only"] and cand["not_approved"] and cand["not_authorized"] and cand["not_executable"]
    assert resume_decision(s,[c1])["will_execute"] is False

def test_resume_interruption_decisions_and_corruption():
    s=mk_session(); c1=mk_cycle(s,1); s=append_engineering_runtime_cycle(s,c1); assert resume_decision(s,[c1])["decision"]=="requires_human_approval"
    s2=mk_session(); c1a=build_engineering_runtime_cycle(session_id=s2["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1)); s2=append_engineering_runtime_cycle(s2,c1a); assert resume_decision(s2,[c1a])["decision"]=="requires_authorization"
    s3=mk_session(); c1z=build_engineering_runtime_cycle(session_id=s3["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1),authorization_reference=ref("authorization",1)); s3=append_engineering_runtime_cycle(s3,c1z); assert resume_decision(s3,[c1z])["decision"]=="requires_execution"
    s4=mk_session(); c1e=build_engineering_runtime_cycle(session_id=s4["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1),authorization_reference=ref("authorization",1),execution_result_reference=ref("execution_result",1)); s4=append_engineering_runtime_cycle(s4,c1e); assert resume_decision(s4,[c1e])["decision"]=="requires_verification"
    ck=build_checkpoint(s4,[c1e],[]); assert resume_decision(s4,[c1e],{**ck,"session_fingerprint":"bad"})["decision"]=="invalid"

def test_inspect_journal_and_persistence(tmp_path):
    s=mk_session(); c1=mk_cycle(s,1,closed=True); s=append_engineering_runtime_cycle(s,c1)
    e1=make_journal_entry(s["session_id"],1,"session_created",None,{"schema":s["schema"],"artifact_identity":s["session_id"],"artifact_fingerprint":s["session_fingerprint"]},None,s["status"])
    e2=make_journal_entry(s["session_id"],2,"cycle_admitted",1,{"schema":c1["schema"],"artifact_identity":c1["cycle_id"],"artifact_fingerprint":c1["cycle_fingerprint"]},e1["entry_fingerprint"],s["status"])
    assert replay_journal([e1,e2],s["session_id"])["event_count"]==2
    out1=inspect_engineering_runtime_session(s,[c1]); out2=inspect_engineering_runtime_session(s,[c1]); assert out1==out2 and "Proposal" in out1["timeline"][0]["line"]
    store=RuntimeSessionStore(tmp_path); store.create(s); store.save_cycle(c1); ck=build_checkpoint(s,[c1],[e1,e2]); store.save_checkpoint(ck); loaded=store.load(s["session_id"]); assert loaded["session"]==s and loaded["checkpoint"]==ck
    with pytest.raises(RuntimeSessionError): store.create(s)
    (tmp_path/s["session_id"]/"session.json").write_text("{bad",encoding="utf-8");
    with pytest.raises(RuntimeSessionError): store.load(s["session_id"])

def test_cli_create_append_inspect_resume(tmp_path):
    ri=tmp_path/"repo.json"; ti=tmp_path/"task.json"; ri.write_text(json.dumps(repo()),encoding="utf-8"); ti.write_text(json.dumps(task()),encoding="utf-8")
    cmd=[sys.executable,"-m","cli.zero_engineering_runtime_session","create","--repository-identity",str(ri),"--task-identity",str(ti),"--store",str(tmp_path/"store")]
    r=subprocess.run(cmd,text=True,capture_output=True); assert r.returncode==0, r.stderr; s=json.loads(r.stdout)
    c=mk_cycle(s,1); cf=tmp_path/"cycle.json"; cf.write_text(json.dumps(c),encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","append-cycle","--store",str(tmp_path/"store"),"--session-id",s["session_id"],"--cycle",str(cf)],text=True,capture_output=True); assert r.returncode==0, r.stdout+r.stderr
    for sub in ("inspect","resume","verify"):
        r=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session",sub,"--store",str(tmp_path/"store"),"--session-id",s["session_id"]],text=True,capture_output=True); assert r.returncode==0; json.loads(r.stdout)
    r=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","inspect","--store",str(tmp_path/"store"),"--session-id","../bad"],text=True,capture_output=True); assert r.returncode!=0

@pytest.mark.parametrize("case", [
    "deterministic_session_creation",
    "cycle_1_linkage",
    "cycle_2_linkage",
    "cycle_3_linkage",
    "cycle_number_skipping_rejection",
    "previous_fingerprint_mismatch",
    "mixed_session_rejection",
    "duplicate_cycle_rejection",
    "approval_reuse_rejection",
    "authorization_reuse_rejection",
    "candidate_only_proposal",
    "resume_awaiting_approval",
    "resume_awaiting_authorization",
    "resume_before_execution",
    "resume_after_execution_before_verification",
    "resume_after_verification_before_feedback",
    "resume_completed",
    "resume_closed",
    "checkpoint_corruption",
    "session_fingerprint_corruption",
    "cycle_fingerprint_corruption",
    "journal_sequence_gap",
    "journal_previous_fingerprint_mismatch",
    "journal_replay_determinism",
    "inspect_read_only",
    "inspect_deterministic",
    "unsafe_persistence_path",
    "corrupt_json",
    "non_canonical_json",
], ids=str)
def test_acceptance_closure_required_cases(case, tmp_path):
    s=mk_session()
    if case=="deterministic_session_creation": assert mk_session()==mk_session(); return
    if case=="cycle_1_linkage": append_engineering_runtime_cycle(s,mk_cycle(s,1)); return
    c1=mk_cycle(s,1,closed=True); s1=append_engineering_runtime_cycle(s,c1)
    if case=="cycle_2_linkage": append_engineering_runtime_cycle(s1,mk_cycle(s1,2,c1)); return
    c2=mk_cycle(s1,2,c1,closed=True); s2=append_engineering_runtime_cycle(s1,c2)
    if case=="cycle_3_linkage": append_engineering_runtime_cycle(s2,mk_cycle(s2,3,c2)); return
    if case=="cycle_number_skipping_rejection":
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,mk_cycle(s1,3,c1))
        return
    if case=="previous_fingerprint_mismatch":
        bad={**mk_cycle(s1,2,c1),"previous_cycle_fingerprint":"bad"}
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,bad)
        return
    if case=="mixed_session_rejection":
        other=create_engineering_runtime_session(repo(),{"task_id":"other"})
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,mk_cycle(other,2,c1))
        return
    if case=="duplicate_cycle_rejection":
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,c1)
        return
    if case=="approval_reuse_rejection":
        bad=build_engineering_runtime_cycle(session_id=s1["session_id"],cycle_number=2,previous_cycle=c1,proposal_reference=ref("proposal",2),approval_reference=c1["approval_reference"])
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,bad)
        return
    if case=="authorization_reuse_rejection":
        bad=build_engineering_runtime_cycle(session_id=s1["session_id"],cycle_number=2,previous_cycle=c1,proposal_reference=ref("proposal",2),approval_reference=ref("approval",2),authorization_reference=c1["authorization_reference"])
        with pytest.raises(RuntimeSessionError): append_engineering_runtime_cycle(s1,bad)
        return
    if case=="candidate_only_proposal":
        cand=build_proposal_candidate(s1,c1,ref("verification_result",1),ref("feedback",1),objective="bounded",bounded_scope=["README.md"])
        assert cand["candidate_only"] and cand["not_executable"] and cand["not_approved"] and cand["not_authorized"]; return
    if case=="resume_awaiting_approval": assert resume_decision(append_engineering_runtime_cycle(mk_session(),mk_cycle(mk_session(),1)),[mk_cycle(mk_session(),1)])["will_execute"] is False; return
    if case=="resume_awaiting_authorization":
        sx=mk_session(); cx=build_engineering_runtime_cycle(session_id=sx["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1)); sx=append_engineering_runtime_cycle(sx,cx); assert resume_decision(sx,[cx])["decision"]=="requires_authorization"; return
    if case=="resume_before_execution":
        sx=mk_session(); cx=build_engineering_runtime_cycle(session_id=sx["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1),authorization_reference=ref("authorization",1)); sx=append_engineering_runtime_cycle(sx,cx); assert resume_decision(sx,[cx])["decision"]=="requires_execution"; return
    if case=="resume_after_execution_before_verification":
        sx=mk_session(); cx=build_engineering_runtime_cycle(session_id=sx["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1),authorization_reference=ref("authorization",1),execution_result_reference=ref("execution_result",1)); sx=append_engineering_runtime_cycle(sx,cx); assert resume_decision(sx,[cx])["decision"]=="requires_verification"; return
    if case=="resume_after_verification_before_feedback":
        sx=mk_session(); cx=build_engineering_runtime_cycle(session_id=sx["session_id"],cycle_number=1,proposal_reference=ref("proposal",1),approval_reference=ref("approval",1),authorization_reference=ref("authorization",1),execution_result_reference=ref("execution_result",1),verification_result_reference=ref("verification_result",1)); sx=append_engineering_runtime_cycle(sx,cx); assert resume_decision(sx,[cx])["decision"]=="requires_feedback_review"; return
    if case=="resume_completed": s3=complete_session(append_engineering_runtime_cycle(s2,mk_cycle(s2,3,c2,closed=True))); assert resume_decision(s3,[])["decision"]=="already_completed"; return
    if case=="resume_closed": s3=close_engineering_runtime_session(complete_session(append_engineering_runtime_cycle(s2,mk_cycle(s2,3,c2,closed=True)))); assert resume_decision(s3,[])["decision"]=="already_closed"; return
    if case=="checkpoint_corruption": assert resume_decision(s1,[c1],{"session_fingerprint":"bad"})["decision"]=="invalid"; return
    if case=="session_fingerprint_corruption": assert resume_decision({**s1,"session_fingerprint":"bad"},[c1])["decision"]=="invalid"; return
    if case=="cycle_fingerprint_corruption": assert resume_decision(s1,[{**c1,"cycle_fingerprint":"bad"}])["decision"]=="invalid"; return
    e1=make_journal_entry(s1["session_id"],1,"session_created",None,{"schema":s1["schema"],"artifact_identity":s1["session_id"],"artifact_fingerprint":s1["session_fingerprint"]},None,s1["status"])
    e2=make_journal_entry(s1["session_id"],2,"cycle_admitted",1,{"schema":c1["schema"],"artifact_identity":c1["cycle_id"],"artifact_fingerprint":c1["cycle_fingerprint"]},e1["entry_fingerprint"],s1["status"])
    if case=="journal_sequence_gap":
        with pytest.raises(RuntimeSessionError): validate_journal([e1,{**e2,"sequence_number":3}],s1["session_id"])
        return
    if case=="journal_previous_fingerprint_mismatch":
        with pytest.raises(RuntimeSessionError): validate_journal([e1,{**e2,"previous_entry_fingerprint":"bad"}],s1["session_id"])
        return
    if case=="journal_replay_determinism": assert replay_journal([e1,e2],s1["session_id"] )==replay_journal([e1,e2],s1["session_id"]); return
    if case=="inspect_read_only":
        store=RuntimeSessionStore(tmp_path); store.create(s1); before=sorted(p.read_text(encoding="utf-8") for p in (tmp_path/s1["session_id"]).rglob("*.json")); inspect_engineering_runtime_session(s1,[c1]); after=sorted(p.read_text(encoding="utf-8") for p in (tmp_path/s1["session_id"]).rglob("*.json")); assert before==after; return
    if case=="inspect_deterministic": assert inspect_engineering_runtime_session(s1,[c1])==inspect_engineering_runtime_session(s1,[c1]); return
    if case=="unsafe_persistence_path":
        with pytest.raises(RuntimeSessionError): RuntimeSessionStore(tmp_path).load("../bad")
        return
    if case=="corrupt_json":
        store=RuntimeSessionStore(tmp_path); store.create(s1); (tmp_path/s1["session_id"]/"session.json").write_text("{bad",encoding="utf-8")
        with pytest.raises(RuntimeSessionError): store.load(s1["session_id"])
        return
    if case=="non_canonical_json":
        store=RuntimeSessionStore(tmp_path); store.create(s1); (tmp_path/s1["session_id"]/"session.json").write_text(json.dumps(s1,indent=2),encoding="utf-8")
        with pytest.raises(RuntimeSessionError): store.load(s1["session_id"])
        return
    raise AssertionError(case)

@pytest.mark.parametrize("case", ["cli_create", "cli_inspect", "cli_resume", "cli_invalid_input_exit_code"], ids=str)
def test_acceptance_closure_cli_cases(case, tmp_path):
    ri=tmp_path/"repo.json"; ti=tmp_path/"task.json"; ri.write_text(json.dumps(repo()),encoding="utf-8"); ti.write_text(json.dumps(task()),encoding="utf-8")
    create_cmd=[sys.executable,"-m","cli.zero_engineering_runtime_session","create","--repository-identity",str(ri),"--task-identity",str(ti),"--store",str(tmp_path/"store")]
    created=subprocess.run(create_cmd,text=True,capture_output=True)
    if case=="cli_create": assert created.returncode==0 and json.loads(created.stdout)["schema"]==SESSION_SCHEMA; return
    assert created.returncode==0
    s=json.loads(created.stdout); c=mk_cycle(s,1); cf=tmp_path/"cycle.json"; cf.write_text(json.dumps(c),encoding="utf-8")
    appended=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","append-cycle","--store",str(tmp_path/"store"),"--session-id",s["session_id"],"--cycle",str(cf)],text=True,capture_output=True)
    assert appended.returncode==0
    if case=="cli_inspect":
        out=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","inspect","--store",str(tmp_path/"store"),"--session-id",s["session_id"]],text=True,capture_output=True)
        assert out.returncode==0 and json.loads(out.stdout)["session_id"]==s["session_id"]; return
    if case=="cli_resume":
        out=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","resume","--store",str(tmp_path/"store"),"--session-id",s["session_id"]],text=True,capture_output=True)
        assert out.returncode==0 and json.loads(out.stdout)["will_execute"] is False; return
    if case=="cli_invalid_input_exit_code":
        out=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_session","inspect","--store",str(tmp_path/"store"),"--session-id","../bad"],text=True,capture_output=True)
        assert out.returncode!=0 and "error" in json.loads(out.stdout); return
    raise AssertionError(case)
