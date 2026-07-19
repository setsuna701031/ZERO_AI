from tests.test_engineering_proposal_review_intake import review_pipeline
def test_scope_expansion_is_blocked(tmp_path):assert review_pipeline(tmp_path,{"scope_expansions":["runtime"]})["scope"]["status"]=="blocked"
