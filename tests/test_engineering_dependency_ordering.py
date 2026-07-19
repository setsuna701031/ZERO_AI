import pytest
from core.engineering.engineering_dependency_ordering import build_engineering_dependency_ordering
def test_order_and_cycle():
 w=[{"work_item_id":"a","evidence_references":["e"]},{"work_item_id":"b","evidence_references":["e"]}]
 assert build_engineering_dependency_ordering(w,[{"predecessor":"a","successor":"b"}])["execution_order"]==["a","b"]
 assert build_engineering_dependency_ordering(w,[{"predecessor":"a","successor":"b"},{"predecessor":"b","successor":"a"}])["cycle_status"]=="cycle_detected"
 with pytest.raises(ValueError):build_engineering_dependency_ordering(w,[{"predecessor":"x","successor":"a"}])
