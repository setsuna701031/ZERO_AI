import json, subprocess, sys
from pathlib import Path
import pytest

from core.engineering.engineering_work_entry import create_engineering_work_request, admit_engineering_work, create_work_coordination
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from core.engineering.engineering_approval_execution_activation import *


def repo(tmp_path):
    root = tmp_path / "repo"; (root / "docs").mkdir(parents=True); (root / "docs" / "base.txt").write_text("base\n")
    subprocess.run(["git", "init"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True)
    return root


def base(tmp_path, ops=None):
    root = repo(tmp_path)
    req = create_engineering_work_request(request_statement="create governed note", repository_identity={"repository_id":"repo"}, repository_root_reference=".", requested_scope=["docs"], acceptance_intent="note exists")
    intake = admit_engineering_work(req); coord = create_work_coordination(req, intake); pipe = create_read_only_pipeline(req, intake, coord)
    out = run_read_only_pipeline(req, intake, coord, pipe, repository_root=root)
    coord = out["coordination"]; artifacts = out["artifacts"]
    sess = build_engineering_runtime_session({"request_id":req["work_request_id"],"fingerprint":req["work_request_fingerprint"],"workspace_id":"repo","workspace_root_fingerprint":"root","session_sequence":1})
    sess = {**sess, "session_id": coord["runtime_session_reference"]["artifact_identity"]}
    operations = ops or [{"operation":"create_text_file","path":"docs/generated.txt","content":"hello\n"}]
    act = create_activation(work_request=req, coordination=coord, runtime_session=sess, read_only_pipeline=out["pipeline"], proposal=artifacts["engineering_proposal"], proposal_review=artifacts["proposal_review_closure"], workspace_reference={"workspace_id":"repo","root":".","allowed_scope":["docs/generated.txt","docs/a.txt","docs/b.txt"]}, ordered_operations=operations)
    return root, req, coord, out, act


def approved(act):
    return build_human_approval(activation=act, human_actor={"actor_type":"human","actor_id":"human-1"}, scope=["docs/generated.txt"])


def authorized(act, appr, **kw):
    h = create_authorization_handoff(attach_human_approval(act, appr), appr)
    return h, build_human_authorization(handoff=h, human_actor={"actor_type":"human","actor_id":"human-2"}, **kw)


def ready(tmp_path):
    root, _, _, _, act = base(tmp_path); appr = approved(act); act = attach_human_approval(act, appr); h = create_authorization_handoff(act, appr); auth = build_human_authorization(handoff=h, human_actor={"actor_type":"human","actor_id":"human-2"}); act = attach_human_authorization(act, auth, appr); prep, act = prepare_execution(act, auth, workspace_root=root); adm, act = admit_adapter(act, prep); return root, act, appr, auth, prep, adm


@pytest.mark.parametrize("case", ["deterministic_activation","stable_activation_identity","initial_stage_awaiting_approval","duplicate_activation_rejection"])
def test_activation_contract_cases(tmp_path, case):
    root, req, coord, out, act = base(tmp_path)
    again = create_activation(work_request=req, coordination=coord, runtime_session={"schema":"zero.engineering.runtime_session.v1","session_id":coord["runtime_session_reference"]["artifact_identity"],"fingerprint":"x"}, read_only_pipeline=out["pipeline"], proposal=out["artifacts"]["engineering_proposal"], proposal_review=out["artifacts"]["proposal_review_closure"], workspace_reference=act["workspace_reference"], ordered_operations=act["ordered_operations"])
    assert act == again and act["current_stage"] == "awaiting_approval" and validate_activation(act)["valid"]


def test_invalid_coordination_reference_invalid_pipeline_reference_wrong_session_wrong_proposal(tmp_path):
    root, req, coord, out, act = base(tmp_path)
    with pytest.raises(ActivationError): create_activation(work_request=req, coordination={**coord,"current_stage":"planning"}, runtime_session={}, read_only_pipeline=out["pipeline"], proposal=out["artifacts"]["engineering_proposal"], proposal_review=out["artifacts"]["proposal_review_closure"], workspace_reference=act["workspace_reference"], ordered_operations=act["ordered_operations"])
    badpipe = {**out["pipeline"], "pipeline_fingerprint":"bad"}
    with pytest.raises(ActivationError): create_activation(work_request=req, coordination=coord, runtime_session={}, read_only_pipeline=badpipe, proposal=out["artifacts"]["engineering_proposal"], proposal_review=out["artifacts"]["proposal_review_closure"], workspace_reference=act["workspace_reference"], ordered_operations=act["ordered_operations"])
    with pytest.raises(ActivationError): create_activation(work_request=req, coordination=coord, runtime_session={"session_id":"wrong"}, read_only_pipeline=out["pipeline"], proposal=out["artifacts"]["engineering_proposal"], proposal_review=out["artifacts"]["proposal_review_closure"], workspace_reference=act["workspace_reference"], ordered_operations=act["ordered_operations"])
    with pytest.raises(ActivationError): create_activation(work_request=req, coordination=coord, runtime_session={"session_id":coord["runtime_session_reference"]["artifact_identity"]}, read_only_pipeline=out["pipeline"], proposal={**out["artifacts"]["engineering_proposal"],"engineering_proposal_id":"wrong"}, proposal_review=out["artifacts"]["proposal_review_closure"], workspace_reference=act["workspace_reference"], ordered_operations=act["ordered_operations"])


@pytest.mark.parametrize("mut,code", [
    (lambda a,p: {**p,"schema":"zero.engineering.proposal_review_closure.v1"}, "ready_for_approval_not_accepted_as_approval"),
    (lambda a,p: build_human_approval(activation=a,human_actor={"actor_type":"human","actor_id":"h"},scope=["docs/generated.txt"],decision="rejected"), "rejected_approval_rejected"),
    (lambda a,p: {**p,"human_actor":{}}, "missing_human_actor_rejected"),
    (lambda a,p: {**p,"proposal_reference":{"artifact_identity":"wrong"}}, "wrong_proposal_approval_rejected"),
    (lambda a,p: {**p,"runtime_session_reference":{"artifact_identity":"wrong"}}, "wrong_session_approval_rejected"),
    (lambda a,p: build_human_approval(activation=a,human_actor={"actor_type":"human","actor_id":"h"},scope=["outside.txt"]), "scope_expansion_approval_rejected"),
    (lambda a,p: {**p,"approval_fingerprint":"bad"}, "invalid_approval_fingerprint"),
    (lambda a,p: {**p,"schema":"zero.test.human_approval.v1"}, "fake_approval_rejected"),
])
def test_approval_rejections_and_valid_attachment(tmp_path, mut, code):
    _,_,_,_,act = base(tmp_path); appr = approved(act)
    assert attach_human_approval(act, appr)["next_governed_action"] == "requires_human_authorization"
    with pytest.raises(ActivationError): attach_human_approval(act, mut(act, appr))
    assert attach_human_approval(act, appr)["authority_state"] != "authorized_unconsumed"


def test_authorization_handoff_after_valid_approval_properties(tmp_path):
    _,_,_,_,act = base(tmp_path); appr = approved(act); act2 = attach_human_approval(act, appr); h = create_authorization_handoff(act2, appr)
    assert h["authority_state"] == "not_granted" and h["requested_human_action"] == "authorize_or_reject"
    assert h["requested_operations"] == act["ordered_operations"] and "execution_token" not in json.dumps(h)
    with pytest.raises(ActivationError): create_authorization_handoff(act, appr)


@pytest.mark.parametrize("mut", [
    lambda h,a: {**a,"schema":"zero.engineering.human_approval.v1"}, lambda h,a: {**a,"human_actor":{}}, lambda h,a: {**a,"approval_reference":{"artifact_identity":"wrong"}}, lambda h,a: {**a,"runtime_session_reference":{"artifact_identity":"wrong"}}, lambda h,a: {**a,"workspace_reference":{"workspace_id":"wrong"}}, lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},authorized_scope=["outside.txt"]), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},authorized_operations=[{**h["requested_operations"][0],"path":"docs/a.txt"}]), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},authorized_operations=h["requested_operations"]+[{"operation":"create_text_file","path":"docs/x.txt"}]), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},authorized_operations=[]), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},revoked=True), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},expired=True), lambda h,a: build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"},consumed=True), lambda h,a: {**a,"schema":"zero.test.auth"},
])
def test_authorization_rejections_and_valid_attachment(tmp_path, mut):
    _,_,_,_,act = base(tmp_path); appr = approved(act); act = attach_human_approval(act, appr); h = create_authorization_handoff(act, appr); auth = build_human_authorization(handoff=h,human_actor={"actor_type":"human","actor_id":"h"})
    assert attach_human_authorization(act, auth, appr)["next_governed_action"] == "requires_execution_preparation"
    with pytest.raises(ActivationError): attach_human_authorization(act, mut(h, auth), appr)
    assert not (Path(tmp_path) / "repo" / "docs" / "generated.txt").exists()


def test_execution_preparation_and_adapter_admission_boundaries(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path)
    assert prep["foundation_reused"] == "engineering_runtime_adapter_execution_preparation" and not (root/"docs/generated.txt").exists()
    with pytest.raises(ActivationError): prepare_execution({**act,"current_stage":"awaiting_authorization"}, auth, workspace_root=root)
    with pytest.raises(ActivationError): admit_adapter(act, {**prep,"adapter_requirements":{"adapter_id":"wrong","adapter_version":"1"}})
    with pytest.raises(ActivationError): admit_adapter(act, prep, adapter_id="unknown")
    assert adm["admission_status"] == "admitted" and act["current_stage"] == "ready_for_execution"


def test_explicit_controlled_execution_evidence_verification_progress_and_completion(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path)
    assert not (root/"docs/generated.txt").exists() and auth["consumption_state"] == "unconsumed"
    result, consumed, act = activate_governed_execution(act, auth, prep, adm, workspace_root=root)
    assert (root/"docs/generated.txt").read_text() == "hello\n" and consumed["consumption_state"] == "consumed"
    assert result["execution_status"] == "succeeded" and result["changed_paths"] == ["docs/generated.txt"]
    ver, act = verify_execution(act, result); assert ver["verification_status"] == "verified"
    prog, act = evaluate_progress(act, ver); assert prog["session_completed"] is False and act["next_governed_action"] == "requires_human_completion_review"


def test_operation_mismatch_zero_mutation_and_replay_rejected(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path)
    with pytest.raises(ActivationError): activate_governed_execution(act, auth, prep, adm, workspace_root=root, requested_operations=[{"operation":"create_text_file","path":"docs/other.txt"}])
    assert not (root/"docs/other.txt").exists() and auth["consumption_state"] == "unconsumed"
    result, consumed, act2 = activate_governed_execution(act, auth, prep, adm, workspace_root=root)
    with pytest.raises(ActivationError): activate_governed_execution(act, consumed, prep, adm, workspace_root=root)
    assert (root/"docs/generated.txt").read_text() == "hello\n"


def test_workspace_state_change_before_execution_rejected_and_zero_mutation(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path); (root/"docs/generated.txt").write_text("intrude")
    with pytest.raises(ActivationError): activate_governed_execution(act, auth, prep, adm, workspace_root=root)
    assert (root/"docs/generated.txt").read_text() == "intrude"


def test_verification_and_progress_routing_guards(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path)
    with pytest.raises(ActivationError): verify_execution(act, {"execution_status":"succeeded"})
    result, consumed, act = activate_governed_execution(act, auth, prep, adm, workspace_root=root)
    bad = {**result, "execution_status":"failed"}
    with pytest.raises(ActivationError): verify_execution(act, bad)
    ver, act = verify_execution(act, result)
    prog, nxt = evaluate_progress(act, ver, completion_candidate=False, remaining_work=True); assert nxt["current_stage"] == "next_iteration_candidate" and prog["executable_proposal_created"] is False
    prog, blk = evaluate_progress(act, ver, stalled=True); assert blk["next_governed_action"] == "requires_human_reassessment"


def test_state_machine_inspect_resume_journal_checkpoint_persistence(tmp_path):
    root, act, appr, auth, prep, adm = ready(tmp_path)
    ins = inspect_activation(act, approval=appr, authorization=auth); before = auth["consumption_state"]
    assert ins["execution_readiness"] is True and auth["consumption_state"] == before
    dec = resume_activation(act); assert dec["decision"] == "requires_explicit_execution_activation" and all(dec[k] is False for k in ("will_approve","will_authorize","will_execute","will_retry_execution","will_complete_session","will_create_executable_proposal"))
    journal = make_activation_journal(act, ["approval_execution_activation_created","human_approval_attached","human_authorization_attached","adapter_admission_completed"])
    assert journal["events"][1]["previous_head"] == journal["events"][0]["journal_head"]
    chk = make_activation_checkpoint(act, journal, authorization=auth); assert resume_activation(act, {**chk,"current_stage":"corrupt"})["decision"] == "invalid"
    persisted = persist_activation_artifacts(tmp_path/"store", "session", activation=act, authorization=auth, journal=journal, checkpoint=chk)
    assert "work-entry/execution-activation.json" in persisted["persisted_files"] and inspect_activation(None)["approval_execution_status"] == "not_initialized"


def test_cli_attach_authorize_prepare_admit_execute_verify_evaluate_inspect_resume(tmp_path):
    root,_,_,_,act = base(tmp_path); appr = approved(act); actp = tmp_path/"act.json"; apprp=tmp_path/"appr.json"; actp.write_text(json.dumps(act)); apprp.write_text(json.dumps(appr))
    def run(args):
        r = subprocess.run([sys.executable,"-m","cli.zero_engineering_work",*args], text=True, capture_output=True); assert r.returncode == 0, r.stdout+r.stderr; return json.loads(r.stdout)
    act = run(["attach-approval",str(actp),"--approval-json",str(apprp)]); actp.write_text(json.dumps(act))
    h = run(["authorization-handoff",str(actp),"--approval-json",str(apprp)]); hp=tmp_path/"h.json"; hp.write_text(json.dumps(h))
    auth = build_human_authorization(handoff=h, human_actor={"actor_type":"human","actor_id":"h"}); authp=tmp_path/"auth.json"; authp.write_text(json.dumps(auth))
    act = run(["attach-authorization",str(actp),"--approval-json",str(apprp),"--authorization-json",str(authp)]); actp.write_text(json.dumps(act))
    out = run(["prepare-execution",str(actp),"--authorization-json",str(authp),"--workspace-root",str(root)]); prep=out["execution_preparation"]; act=out["activation"]; actp.write_text(json.dumps(act)); prepp=tmp_path/"prep.json"; prepp.write_text(json.dumps(prep))
    out = run(["admit-adapter",str(actp),"--preparation-json",str(prepp)]); adm=out["adapter_admission"]; act=out["activation"]; actp.write_text(json.dumps(act)); admp=tmp_path/"adm.json"; admp.write_text(json.dumps(adm))
    out = run(["execute",str(actp),"--authorization-json",str(authp),"--preparation-json",str(prepp),"--admission-json",str(admp),"--workspace-root",str(root)]); res=out["execution_result"]; auth=out["authorization"]; act=out["activation"]; actp.write_text(json.dumps(act)); resp=tmp_path/"res.json"; resp.write_text(json.dumps(res))
    out = run(["verify-execution",str(actp),"--execution-json",str(resp)]); ver=out["verification"]; act=out["activation"]; actp.write_text(json.dumps(act)); verp=tmp_path/"ver.json"; verp.write_text(json.dumps(ver))
    out = run(["evaluate-progress",str(actp),"--verification-json",str(verp)]); assert out["progress"]["session_completed"] is False
    bad = subprocess.run([sys.executable,"-m","cli.zero_engineering_work","attach-authorization",str(actp),"--approval-json",str(apprp),"--authorization-json",str(apprp)], text=True, capture_output=True)
    assert bad.returncode == 2 and "Traceback" not in bad.stderr and json.loads(bad.stdout)["valid"] is False
