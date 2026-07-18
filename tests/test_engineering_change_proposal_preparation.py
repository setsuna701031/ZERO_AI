from core.engineering.change_proposal_preparation import prepare_change_proposal
from tests.test_engineering_planning_request import planning
def preparation():return prepare_change_proposal(planning())
def test_preparation_is_not_a_proposal_or_mutation_plan():
 p=preparation();x=p["preparation_payload"];assert p["status"]=="prepared" and x["proposal_status"]=="not_created" and x["change_limits"]["mutation_allowed"] is False and p["boundary"]["proposal_created"] is False
