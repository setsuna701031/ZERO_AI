import pytest
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake
from core.engineering.engineering_proposal_scope import build_engineering_proposal_scope
from core.engineering.engineering_proposed_change_set import build_engineering_proposed_change_set
from tests.test_engineering_proposal_intake import proposal_planning_closure
def test_change_is_intent_not_payload(tmp_path):
 s=build_engineering_proposal_scope(build_engineering_proposal_intake(proposal_planning_closure(tmp_path)));c=build_engineering_proposed_change_set(s)[0]
 assert c["implementation_authority"]==c["mutation_authority"]=="not_granted" and not ({"patch","diff","before","after"}&set(c))
 bad={"goal_id":s["included_goals"][0],"work_item_id":s["included_work_items"][0],"change_category":"source_change","target_repository_area":s["included_repository_areas"][0],"change_objective":"x","current_state_evidence":s["evidence_references"],"diff":"x"}
 with pytest.raises(ValueError):build_engineering_proposed_change_set(s,{"changes":[bad]})
 bad.pop("diff");bad["current_state_evidence"]=[]
 with pytest.raises(ValueError):build_engineering_proposed_change_set(s,{"changes":[bad]})
