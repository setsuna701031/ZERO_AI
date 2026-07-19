from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_mutation_transaction_common import *

def emit(o): print(canonical_json(o))

def pipeline(p):
    if 'authorization_decision' not in p and 'decision' not in p: return {'error':{'code':'authorization_decision_required'}}
    up=p.get('upstream',p)
    pol=build_mutation_authorization_policy(p.get('authorization_policy',{}))
    req=build_mutation_authorization_request(up['mutation_handoff'],up['preparation_closure'],up['readiness_verification'],up['preparation_token'],up['token_eligibility'],up['mutation_package'],up['package_validation'],up['approval_verification'],up['approved_scope'],p.get('authorization_request',{}))
    elig=evaluate_mutation_authorization_eligibility(pol,req,up['mutation_handoff'],up['preparation_closure'],up['readiness_verification'],up['preparation_token'],up['token_eligibility'],up['mutation_package'],up['package_validation'],up['approval_verification'],up['approved_scope'])
    dec=build_mutation_authorization_decision(p.get('authorization_decision',p.get('decision',{})),pol,req,elig,up['mutation_package'])
    scope=seal_mutation_authorized_scope(dec,req,up['mutation_package'])
    ver=verify_mutation_authorization(pol,req,elig,dec,scope,up['mutation_package'])
    telig=evaluate_mutation_authorization_token_eligibility(ver,dec,scope,up['mutation_package'],up['preparation_token'],p.get('consumed_authorization_token_record'))
    tok=issue_mutation_authorization_token(telig,ver,dec,scope,up['mutation_package'],up['preparation_token'],p.get('authorization_sequence',0))
    tpol=build_mutation_transaction_policy(p.get('transaction_policy',{}))
    adm=admit_mutation_transaction(tpol,ver,telig,tok,scope,up['mutation_package'],up['package_validation'],up['preparation_token'])
    plan=build_mutation_transaction_plan(adm,up['mutation_package'],tok,scope)
    atomic=build_mutation_atomicity_plan(plan,tpol)
    backup=build_mutation_backup_plan(plan,tpol)
    rollback=build_mutation_rollback_plan(plan,backup)
    commit=define_mutation_commit_boundary(plan,atomic,backup,rollback)
    recovery=build_mutation_recovery_plan(plan,backup,rollback,commit,tpol)
    txpkg=assemble_mutation_transaction_package(pol,req,elig,dec,scope,ver,telig,tok,tpol,adm,plan,atomic,backup,rollback,commit,recovery,up['mutation_package'],up['package_validation'],p.get('transaction_sequence',0))
    txval=validate_mutation_transaction_package(txpkg,scope,ver,tok,adm,plan,atomic,backup,rollback,commit,recovery)
    ready=verify_mutation_transaction_readiness(txpkg,txval,ver,telig,tok,tpol,adm,plan,atomic,backup,rollback,commit,recovery)
    hand=build_mutation_executor_handoff(txpkg,txval,ready,tok,up['preparation_token'],up['mutation_package'],dec,scope,plan,atomic,backup,rollback,commit,recovery)
    ev=build_mutation_transaction_evidence(pol,req,elig,dec,scope,ver,telig,tok,tpol,adm,plan,atomic,backup,rollback,commit,recovery,txpkg,txval,ready,hand)
    clo=close_mutation_transaction(hand,txpkg,txval,ready,ver,telig,tok,adm,plan,atomic,backup,rollback,commit,recovery,ev)
    return {'authorization_policy':pol,'authorization_request':req,'authorization_eligibility':elig,'authorization_decision':dec,'authorized_scope':scope,'authorization_verification':ver,'token_eligibility':telig,'authorization_token':tok,'transaction_policy':tpol,'transaction_admission':adm,'transaction_plan':plan,'atomicity_plan':atomic,'backup_plan':backup,'rollback_plan':rollback,'commit_boundary':commit,'recovery_plan':recovery,'transaction_package':txpkg,'package_validation':txval,'readiness_verification':ready,'executor_handoff':hand,'evidence':ev,'closure':clo}

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('--json',default='{}'); ns=ap.parse_args(argv)
    try:
        p=json.loads(ns.json or '{}'); a=ns.action
        if a=='pipeline': o=pipeline(p)
        elif a in ('inspect','validate'): o={'schemas':SCHEMAS,'actions':['authorization-policy','authorization-request','authorization-eligibility','authorization-decision','authorized-scope','authorization-verification','token-eligibility','issue-token','transaction-policy','transaction-admission','transaction-plan','atomicity-plan','backup-plan','rollback-plan','commit-boundary','recovery-plan','transaction-package','validate-package','verify-readiness','executor-handoff','evidence','closure','validate','inspect','pipeline']}
        elif a=='authorization-policy': o=build_mutation_authorization_policy(p)
        elif a=='authorization-request': o=build_mutation_authorization_request(p['mutation_handoff'],p['preparation_closure'],p['readiness_verification'],p['preparation_token'],p['token_eligibility'],p['mutation_package'],p['package_validation'],p['approval_verification'],p['approved_scope'],p)
        elif a=='authorization-eligibility': o=evaluate_mutation_authorization_eligibility(p['policy'],p['request'],p['mutation_handoff'],p['preparation_closure'],p['readiness_verification'],p['preparation_token'],p['token_eligibility'],p['mutation_package'],p['package_validation'],p['approval_verification'],p['approved_scope'])
        elif a=='authorization-decision': o=build_mutation_authorization_decision(p.get('decision',{}),p['policy'],p['request'],p['eligibility'],p['mutation_package'])
        elif a=='authorized-scope': o=seal_mutation_authorized_scope(p['decision'],p['request'],p['mutation_package'])
        elif a=='authorization-verification': o=verify_mutation_authorization(p['policy'],p['request'],p['eligibility'],p['decision'],p['authorized_scope'],p['mutation_package'])
        elif a=='token-eligibility': o=evaluate_mutation_authorization_token_eligibility(p['verification'],p['decision'],p['authorized_scope'],p['mutation_package'],p['preparation_token'],p.get('consumed_token_record'))
        elif a=='issue-token': o=issue_mutation_authorization_token(p['eligibility'],p['verification'],p['decision'],p['authorized_scope'],p['mutation_package'],p['preparation_token'],p.get('authorization_sequence',0))
        elif a=='transaction-policy': o=build_mutation_transaction_policy(p)
        else: o={'error':{'code':'unknown_action'}}
        emit(o); return 0 if 'error' not in o else 2
    except Exception:
        emit({'error':{'code':'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
