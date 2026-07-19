from tests.test_engineering_proposal_review_intake import review_pipeline
def test_dependency_cycle_is_blocked(tmp_path):assert review_pipeline(tmp_path,{"dependency_cycles":["a->a"]})["dependencies"]["status"]=="blocked"
