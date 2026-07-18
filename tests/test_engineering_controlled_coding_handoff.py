from core.engineering.controlled_coding_handoff import build_controlled_coding_handoff
from tests.test_engineering_change_proposal_preparation import preparation
def handoff():return build_controlled_coding_handoff(preparation())
def test_handoff_is_complete_but_coding_not_started():
 h=handoff();assert h["status"]=="handed_off" and h["handoff_payload"]["next_stage"]=="repository_analysis_pending" and h["handoff_payload"]["intent_types"] and h["boundary"]["developer_intake_complete"] is True and h["boundary"]["coding_started"] is False
