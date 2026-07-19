from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_governed_execution_intake import build_engineering_governed_execution_intake
from core.engineering.engineering_execution_admission import build_engineering_execution_admission
from core.engineering.engineering_execution_session import build_engineering_execution_session
from core.engineering.engineering_runtime_handoff import build_engineering_runtime_handoff
from core.engineering.engineering_execution_observation import build_engineering_execution_observation
from core.engineering.engineering_execution_evidence import build_engineering_execution_evidence
from core.engineering.engineering_execution_outcome import build_engineering_execution_outcome
from core.engineering.engineering_governed_execution_verification import build_engineering_governed_execution_verification
from core.engineering.engineering_governed_execution_closure import build_engineering_governed_execution_closure

STAGES=("intake","admission","session","handoff","observation","evidence","outcome","verification","closure")
def _read(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_pipeline(preparation_closure,intent=None,runtime_result=None):
 intake=build_engineering_governed_execution_intake(preparation_closure,intent);admission=build_engineering_execution_admission(intake);session=build_engineering_execution_session(admission,intake);handoff=build_engineering_runtime_handoff(session)
 observation=build_engineering_execution_observation(session,handoff,runtime_result);evidence=build_engineering_execution_evidence(session,observation,runtime_result);outcome=build_engineering_execution_outcome(session,handoff,observation,evidence);verification=build_engineering_governed_execution_verification(intake,admission,session,handoff,observation,evidence,outcome);closure=build_engineering_governed_execution_closure(intake,session,handoff,evidence,outcome,verification)
 return dict(zip(STAGES,(intake,admission,session,handoff,observation,evidence,outcome,verification,closure)))
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("execution_preparation_closure_json");p.add_argument("--intent");p.add_argument("--runtime-result");p.add_argument("--stage",choices=STAGES,default="closure");return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  artifacts=build_pipeline(_read(a.execution_preparation_closure_json),_read(a.intent) if a.intent else {},_read(a.runtime_result) if a.runtime_result else None);value=artifacts[a.stage];return value,0 if value.get("status") in {"accepted","admitted","prepared","observed","completed","verified","closed_completed"} else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","build_pipeline","main","run"]
