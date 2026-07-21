from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from .engineering_runtime_orchestrator_common import canonical_json, SAFE_RELATIVE
ALLOWED_FILES=("request.json","session.json","phase.json","checkpoints.json","artifact-index.json","formal-analysis.json","formal-planning.json","formal-proposal.json","formal-approval.json","formal-authorization.json","formal-preparation.json","result.json","verification.json","evidence.json","closure.json","work-entry/request.json","work-entry/intake.json","work-entry/coordination.json","work-entry/human-gate-handoff.json","work-entry/pipeline.json","work-entry/checkpoint.json","work-entry/journal.json","work-entry/stages/repository-admission.json","work-entry/stages/repository-analysis.json","work-entry/stages/objective-definition.json","work-entry/stages/planning.json","work-entry/stages/proposal-preparation.json","work-entry/stages/proposal-review.json","work-entry/natural-language-intake.json","work-entry/finalized-natural-language-intake.json","work-entry/intake-repository-evidence.json","work-entry/specification-candidate.json","work-entry/specification-clarification.json","work-entry/specification-clarification-response.json","work-entry/specification-confirmation.json","work-entry/operator-flow.json","work-entry/operator-status.json","work-entry/execution-activation.json","work-entry/approval.json","work-entry/authorization-handoff.json","work-entry/authorization.json","work-entry/execution-preparation.json","work-entry/adapter-admission.json","work-entry/execution-result.json","work-entry/verification.json","work-entry/progress.json","work-entry/execution-journal.json","work-entry/execution-checkpoint.json","work-entry/governed-change-package.json","execution/practical-execution-evidence.json","execution/bounded-test-policy.json","execution/test-results.json","verification/practical-verification.json","planning/multifile-change-plan-candidate.json","planning/multifile-change-plan-confirmation.json","testing/bounded-test-set-result.json","testing/test-failure-evidence.json","feedback/repair-proposal-candidate.json","feedback/repair-candidate-review.json","iterations/iteration-index.json","reproduction/request.json","reproduction/confirmation.json","reproduction/admission.json","reproduction/result.json","testing/test-set-result.json","testing/failure-evidence.json","feedback/repair-candidate.json","feedback/repair-review.json")
ALLOWED_FILES=ALLOWED_FILES+("reproduction/workspace-snapshot.json","repair/planning-intake.json","repair/root-cause-hypothesis.json","repair/impact-analysis.json","repair/strategy-candidate.json","repair/patch-candidate.json","repair/patch-validation.json","repair/patch-review.json")
def _path(root,session_id,name):
    if name not in ALLOWED_FILES or not SAFE_RELATIVE.fullmatch(session_id): raise ValueError("unsafe_session_store_name")
    return Path(root).resolve()/session_id/name
def write_session_artifact(root,session_id,name,value):
    target=_path(root,session_id,name); target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".runtime-",suffix=".json",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f: f.write(canonical_json(value)+"\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return name
def read_session_artifact(root,session_id,name):
    p=_path(root,session_id,name)
    with p.open("r",encoding="utf-8") as f: value=json.load(f)
    if canonical_json(value)+"\n"!=p.read_text(encoding="utf-8"): raise ValueError("non_canonical_session_json")
    return value
def load_session_store(root,session_id): return {n:read_session_artifact(root,session_id,n) for n in ALLOWED_FILES if _path(root,session_id,n).exists()}
