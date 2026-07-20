from __future__ import annotations
import json, sys
from core.engineering.engineering_feedback_controller import *
from core.engineering.engineering_failure_analysis_validation import validate_failure_analysis
from core.engineering.engineering_repair_continuation_eligibility_validation import validate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_cycle_validation import validate_repair_continuation_cycle
from core.engineering.engineering_feedback_report_validation import validate_feedback_report
CMDS={'build-failure-analysis':build_failure_analysis,'validate-failure-analysis':validate_failure_analysis,'evaluate-eligibility':evaluate_repair_continuation_eligibility,'validate-eligibility':validate_repair_continuation_eligibility,'create-cycle':create_repair_continuation_cycle,'validate-cycle':validate_repair_continuation_cycle,'build-candidate':build_continuation_candidate,'build-plan':build_continuation_plan,'build-proposal':build_continuation_proposal,'build-proposal-linkage':build_continuation_proposal_linkage,'inspect-cycle':inspect_repair_continuation,'resume-cycle':resume_repair_continuation,'build-report':build_feedback_report,'validate-report':validate_feedback_report}
def main(argv=None):
    argv=argv or sys.argv[1:]
    if len(argv)!=1 or argv[0] not in CMDS:
        print(json.dumps({'ok':False,'error':'unknown_command'},sort_keys=True), file=sys.stderr); return 2
    try:
        payload=json.load(sys.stdin)
        if not isinstance(payload,dict): raise ValueError('json_object_required')
        res=CMDS[argv[0]](**payload) if argv[0].startswith(('build','evaluate','create','validate')) else CMDS[argv[0]](payload)
        if hasattr(res,'valid'): res={'valid':res.valid,'errors':list(res.errors)}
        print(json.dumps(res, sort_keys=True, separators=(',',':'))); return 0
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},sort_keys=True), file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())
