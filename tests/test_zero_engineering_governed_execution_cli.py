from cli.zero_engineering_governed_execution import STAGES, build_pipeline
def test_cli_pipeline_all_stages_and_no_result_behavior():
 value=build_pipeline({}, {}, None)
 assert tuple(value)==STAGES and value["closure"]["status"]=="insufficient_evidence"
