import pytest
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake
from core.engineering.engineering_proposal_scope import build_engineering_proposal_scope
from tests.test_engineering_proposal_intake import proposal_planning_closure
def test_scope_is_contained(tmp_path):
 i=build_engineering_proposal_intake(proposal_planning_closure(tmp_path));s=build_engineering_proposal_scope(i);assert all(s["containment_checks"].values())
 with pytest.raises(ValueError):build_engineering_proposal_scope(i,{"change_categories":["delete_everything"]})
