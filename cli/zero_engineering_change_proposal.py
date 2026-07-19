from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_change_intent import build_change_intent
from core.engineering.engineering_change_workspace_evidence import bind_workspace_evidence
from core.engineering.engineering_change_target_admission import admit_change_target
from core.engineering.engineering_change_scope_policy import build_change_scope_policy
from core.engineering.engineering_change_file_precondition import build_file_precondition
from core.engineering.engineering_change_operation import build_change_operation
from core.engineering.engineering_change_content import build_proposed_content
from core.engineering.engineering_change_diff import build_change_diff
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_change_proposal_validation import validate_change_proposal
from core.engineering.engineering_change_proposal_safety_review import review_change_proposal_safety
from core.engineering.engineering_change_proposal_verification import verify_change_proposal
from core.engineering.engineering_change_proposal_evidence import build_change_proposal_evidence
from core.engineering.engineering_change_proposal_approval_handoff import build_approval_handoff
from core.engineering.engineering_change_proposal_closure import close_change_proposal
from core.engineering.engineering_change_proposal_common import canonical_json, SCHEMAS

def emit(obj):
 print(canonical_json(obj))
def load_payload(raw):
 return json.loads(raw or '{}')
def pipeline(p):
 intent=build_change_intent(p.get('intent',{})); we=bind_workspace_evidence(p.get('workspace_evidence',{})); policy=build_change_scope_policy(p.get('scope_policy',{}),p.get('parent_scope_policy'))
 admissions=[admit_change_target(x,policy) for x in p.get('targets',intent.get('requested_target_paths',[]))]
 ev_by_path={we.get('observed_relative_path'):we}; pres=[]; contents=[]; ops=[]; diffs=[]
 for item in p.get('changes',[]):
  ev=ev_by_path.get(item.get('target_relative_path'))
  pre=build_file_precondition(item.get('precondition',{'relative_path':item.get('target_relative_path'),'conditions':{'expected_missing':item.get('operation_type')=='create_text_file'},'expected_workspace_id':we.get('workspace_id'),'expected_workspace_root_fingerprint':we.get('workspace_root_fingerprint')}),ev); pres.append(pre)
  cont=None
  if 'content' in item:
   cont=build_proposed_content({'content':item.get('content'),'metadata':item.get('metadata',{})},policy); contents.append(cont)
  adm=next((a for a in admissions if a.get('target_relative_path')==item.get('target_relative_path')),admit_change_target(item.get('target_relative_path'),policy))
  op=build_change_operation({'operation_type':item.get('operation_type'),'source_relative_path':item.get('source_relative_path'),'target_relative_path':item.get('target_relative_path'),'target_admission_id':adm.get('target_admission_id'),'target_admission_fingerprint':adm.get('fingerprint'),'precondition_id':pre.get('precondition_id'),'precondition_fingerprint':pre.get('fingerprint'),'proposed_content_id':cont and cont.get('content_id'),'proposed_content_fingerprint':cont and cont.get('fingerprint'),'expected_before_fingerprint':ev and ev.get('observed_content_sha256'),'proposed_after_fingerprint':cont and cont.get('content_sha256')}); ops.append(op)
  diffs.append(build_change_diff({'operation_type':item.get('operation_type'),'target_relative_path':item.get('target_relative_path'),'source_relative_path':item.get('source_relative_path'),'before_content':item.get('before_content',''),'after_content':item.get('content',''),'after_sha256':cont and cont.get('content_sha256')},policy))
 prop=assemble_change_proposal({'intent':intent,'workspace_evidence':we,'target_admissions':admissions,'scope_policy':policy,'preconditions':pres,'operations':ops,'contents':contents,'diffs':diffs,'authority_constraints':intent.get('authority_constraints',[]),'validation_requirements':intent.get('expected_validation_identifiers',[])})
 val=validate_change_proposal(prop); saf=review_change_proposal_safety(prop,val); ver=verify_change_proposal(prop,val,saf); evd=build_change_proposal_evidence(prop,val,saf,ver); hand=build_approval_handoff(prop,ver,saf); clo=close_change_proposal(prop,val,saf,ver,hand)
 return {'intent':intent,'workspace_evidence':we,'scope_policy':policy,'target_admissions':admissions,'preconditions':pres,'contents':contents,'operations':ops,'diffs':diffs,'proposal':prop,'validation':val,'safety_review':saf,'verification':ver,'evidence':evd,'approval_handoff':hand,'closure':clo}
def main(argv=None):
 ap=argparse.ArgumentParser(add_help=True); ap.add_argument('action'); ap.add_argument('--json',default='{}'); ns=ap.parse_args(argv)
 try:
  p=load_payload(ns.json); a=ns.action
  if a=='intent': obj=build_change_intent(p)
  elif a=='workspace-evidence': obj=bind_workspace_evidence(p)
  elif a=='target-admission': obj=admit_change_target(p.get('path'),p.get('policy',{}))
  elif a=='scope-policy': obj=build_change_scope_policy(p,p.get('parent'))
  elif a=='file-precondition': obj=build_file_precondition(p.get('precondition',p),p.get('evidence'))
  elif a=='operation': obj=build_change_operation(p)
  elif a=='content': obj=build_proposed_content(p,p.get('policy',{}))
  elif a=='diff': obj=build_change_diff(p,p.get('policy',{}))
  elif a=='proposal': obj=assemble_change_proposal(p)
  elif a=='validate-proposal': obj=validate_change_proposal(p.get('proposal',p))
  elif a=='safety-review': obj=review_change_proposal_safety(p['proposal'],p['validation'])
  elif a=='verify': obj=verify_change_proposal(p['proposal'],p['validation'],p['safety_review'])
  elif a=='evidence': obj=build_change_proposal_evidence(p['proposal'],p['validation'],p['safety_review'],p['verification'])
  elif a=='approval-handoff': obj=build_approval_handoff(p['proposal'],p['verification'],p['safety_review'])
  elif a=='closure': obj=close_change_proposal(p['proposal'],p['validation'],p['safety_review'],p['verification'],p['approval_handoff'])
  elif a in ('pipeline','inspect'): obj=pipeline(p) if a=='pipeline' else {'schemas':SCHEMAS,'actions':['intent','workspace-evidence','target-admission','scope-policy','file-precondition','operation','content','diff','proposal','validate-proposal','safety-review','verify','evidence','approval-handoff','closure','inspect','pipeline']}
  else: obj={'error':{'code':'unknown_action'}}
  emit(obj); return 0 if 'error' not in obj else 2
 except Exception:
  emit({'error':{'code':'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
