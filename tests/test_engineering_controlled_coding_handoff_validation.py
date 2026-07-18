from copy import deepcopy
from core.engineering.engineering_intake_common import identified
from core.engineering.controlled_coding_handoff_validation import validate_controlled_coding_handoff
from tests.test_engineering_controlled_coding_handoff import handoff
from tests.test_engineering_change_proposal_preparation import preparation
def _fp(v):return identified({k:x for k,x in v.items() if k not in {"controlled_coding_handoff_id","fingerprint"}},"controlled_coding_handoff_id","engineering-controlled-coding-handoff-")
def test_handoff_lineage_and_refingerprinted_tamper():
 h=handoff();assert validate_controlled_coding_handoff(h,preparation()).valid and len([k for k in h if k.endswith("_fingerprint") and k.startswith("source_")])==5
 bad=deepcopy(h);bad["handoff_payload"]["next_stage"]="coding";assert not validate_controlled_coding_handoff(_fp(bad),preparation()).valid
def test_coding_and_approval_promotion_rejected():
 bad=deepcopy(handoff());bad["boundary"]["coding_started"]=True;assert not validate_controlled_coding_handoff(_fp(bad)).valid
