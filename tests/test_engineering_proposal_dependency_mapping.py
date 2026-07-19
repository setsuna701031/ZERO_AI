from copy import deepcopy
import pytest
from core.engineering.engineering_proposal_dependency_mapping import build_engineering_proposal_dependency_mapping
def test_dependency_order_cycle_and_missing():
 c=[{"proposed_change_id":"a","work_item_id":"wa"},{"proposed_change_id":"b","work_item_id":"wb"}]
 assert build_engineering_proposal_dependency_mapping(c,[{"predecessor":"a","successor":"b"}])["ordering_constraints"]==["a","b"]
 assert build_engineering_proposal_dependency_mapping(c,[{"predecessor":"a","successor":"b"},{"predecessor":"b","successor":"a"}])["cycle_status"]=="cycle_detected"
 with pytest.raises(ValueError):build_engineering_proposal_dependency_mapping(c,[{"predecessor":"x","successor":"a"}])
