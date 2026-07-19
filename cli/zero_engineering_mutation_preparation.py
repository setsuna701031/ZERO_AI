from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_mutation_preparation_common import canonical_json,SCHEMAS
from core.engineering.engineering_operator_approval_policy import build_operator_approval_policy
from core.engineering.engineering_operator_approval_request import build_operator_approval_request
from core.engineering.engineering_operator_approval_eligibility import evaluate_operator_approval_eligibility
from core.engineering.engineering_operator_approval_decision import build_operator_approval_decision
from core.engineering.engineering_operator_approved_scope import seal_operator_approved_scope
from core.engineering.engineering_operator_approval_verification import verify_operator_approval
from core.engineering.engineering_mutation_preparation_policy import build_mutation_preparation_policy
from core.engineering.engineering_mutation_preparation_request import build_mutation_preparation_request
from core.engineering.engineering_mutation_preparation_admission import admit_mutation_preparation
from core.engineering.engineering_prepared_mutation_operation import build_prepared_mutation_operation
from core.engineering.engineering_mutation_package import assemble_mutation_package
from core.engineering.engineering_mutation_package_validation import validate_mutation_package
from core.engineering.engineering_mutation_preparation_token_eligibility import evaluate_mutation_preparation_token_eligibility
from core.engineering.engineering_mutation_preparation_token import issue_mutation_preparation_token
from core.engineering.engineering_mutation_readiness_verification import verify_mutation_readiness
from core.engineering.engineering_mutation_handoff import build_mutation_handoff
from core.engineering.engineering_mutation_preparation_evidence import build_mutation_preparation_evidence
from core.engineering.engineering_mutation_preparation_closure import close_mutation_preparation

def emit(o): print(canonical_json(o))
def pipeline(p):
 if 'decision' not in p: return {'error':{'code':'operator_decision_required'}}
 pol=build_operator_approval_policy(p.get('approval_policy',{})); req=build_operator_approval_request(p); el=evaluate_operator_approval_eligibility(pol,req,p.get('proposal',{}),p.get('validation',{}),p.get('safety_review',{}),p.get('verification',{}),p.get('closure',{}),p.get('approval_handoff',{}))
 dec=build_operator_approval_decision(p['decision'],pol,req,el,p.get('proposal',{})); scope=seal_operator_approved_scope(dec,req,p.get('proposal',{})); av=verify_operator_approval(pol,req,el,dec,scope,p.get('proposal',{}))
 mpol=build_mutation_preparation_policy(p.get('preparation_policy',{})); mreq=build_mutation_preparation_request(mpol,av,scope,p.get('proposal',{}),p.get('preparation_request',{})); adm=admit_mutation_preparation(mpol,mreq,av,dec,scope,p.get('proposal',{}))
 from core.engineering.engineering_mutation_preparation_common import selected_ops
 pops=[build_prepared_mutation_operation(o,p.get('proposal',{}),scope,dec,adm,i) for i,o in enumerate(selected_ops(p.get('proposal',{}),scope.get('approved_operation_ids',[])))]
 pkg=assemble_mutation_package(pol,req,el,dec,scope,av,mpol,mreq,adm,pops,p.get('proposal',{}),p.get('package_sequence',0)); val=validate_mutation_package(pkg,p.get('proposal',{}),scope,av,adm); tel=evaluate_mutation_preparation_token_eligibility(pkg,val,av,scope,adm,p.get('consumed_token_record')); tok=issue_mutation_preparation_token(tel,pkg,val,av,scope,p.get('preparation_sequence',0)); ready=verify_mutation_readiness(pkg,val,av,scope,adm,tel,tok); hand=build_mutation_handoff(pkg,val,ready,tok,p.get('proposal',{}),dec,scope); ev=build_mutation_preparation_evidence(pkg,val,ready,tok,hand,dec,scope); clo=close_mutation_preparation(hand,pkg,val,ready,tel,tok,av,scope,adm,ev)
 return {'approval_policy':pol,'approval_request':req,'approval_eligibility':el,'operator_decision':dec,'approved_scope':scope,'approval_verification':av,'preparation_policy':mpol,'preparation_request':mreq,'preparation_admission':adm,'prepared_operations':pops,'mutation_package':pkg,'package_validation':val,'token_eligibility':tel,'preparation_token':tok,'readiness_verification':ready,'mutation_handoff':hand,'evidence':ev,'closure':clo}
def main(argv=None):
 ap=argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('--json',default='{}'); ns=ap.parse_args(argv)
 try:
  p=json.loads(ns.json or '{}'); a=ns.action
  if a=='pipeline': o=pipeline(p)
  elif a in ('inspect','validate'): o={'schemas':SCHEMAS,'actions':['approval-policy','approval-request','approval-eligibility','approval-decision','approved-scope','approval-verification','preparation-policy','preparation-request','preparation-admission','prepared-operation','mutation-package','validate-package','token-eligibility','issue-token','verify-readiness','mutation-handoff','evidence','closure','validate','inspect','pipeline']}
  elif a=='approval-policy': o=build_operator_approval_policy(p)
  elif a=='approval-request': o=build_operator_approval_request(p)
  elif a=='approval-eligibility': o=evaluate_operator_approval_eligibility(p['policy'],p['request'],p['proposal'],p['validation'],p['safety_review'],p['verification'],p['closure'],p['approval_handoff'])
  elif a=='approval-decision': o=build_operator_approval_decision(p.get('decision',{}),p['policy'],p['request'],p['eligibility'],p['proposal'])
  elif a=='approved-scope': o=seal_operator_approved_scope(p['decision'],p['request'],p['proposal'])
  elif a=='approval-verification': o=verify_operator_approval(p['policy'],p['request'],p['eligibility'],p['decision'],p['approved_scope'],p['proposal'])
  elif a=='preparation-policy': o=build_mutation_preparation_policy(p)
  elif a=='preparation-request': o=build_mutation_preparation_request(p['policy'],p['approval_verification'],p['approved_scope'],p['proposal'],p)
  elif a=='preparation-admission': o=admit_mutation_preparation(p['policy'],p['request'],p['approval_verification'],p['decision'],p['approved_scope'],p['proposal'])
  elif a=='prepared-operation': o=build_prepared_mutation_operation(p['operation'],p['proposal'],p['approved_scope'],p['decision'],p['admission'],p.get('sequence_index',0))
  elif a=='mutation-package': o=assemble_mutation_package(p['policy'],p['request'],p['eligibility'],p['decision'],p['approved_scope'],p['approval_verification'],p['preparation_policy'],p['preparation_request'],p['admission'],p['prepared_operations'],p['proposal'],p.get('package_sequence',0))
  elif a=='validate-package': o=validate_mutation_package(p['package'],p['proposal'],p['approved_scope'],p['approval_verification'],p['admission'])
  elif a=='token-eligibility': o=evaluate_mutation_preparation_token_eligibility(p['package'],p['package_validation'],p['approval_verification'],p['approved_scope'],p['admission'],p.get('consumed_token_record'))
  elif a=='issue-token': o=issue_mutation_preparation_token(p['eligibility'],p['package'],p['package_validation'],p['approval_verification'],p['approved_scope'],p.get('preparation_sequence',0))
  elif a=='verify-readiness': o=verify_mutation_readiness(p['package'],p['package_validation'],p['approval_verification'],p['approved_scope'],p['admission'],p['token_eligibility'],p['token'])
  elif a=='mutation-handoff': o=build_mutation_handoff(p['package'],p['package_validation'],p['readiness'],p['token'],p['proposal'],p['decision'],p['approved_scope'])
  elif a=='evidence': o=build_mutation_preparation_evidence(p['package'],p['package_validation'],p['readiness'],p['token'],p['handoff'],p['decision'],p['approved_scope'])
  elif a=='closure': o=close_mutation_preparation(p['handoff'],p['package'],p['package_validation'],p['readiness'],p['token_eligibility'],p['token'],p['approval_verification'],p['approved_scope'],p['admission'],p['evidence'])
  else: o={'error':{'code':'unknown_action'}}
  emit(o); return 0 if 'error' not in o else 2
 except Exception: emit({'error':{'code':'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
