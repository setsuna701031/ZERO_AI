from cli.zero_mission_planner import parser
def test_commands_and_no_forbidden_flags():
 text=parser().format_help()
 for command in ("plan","plan-file","validate","status","create-mission","replan"):assert command in text
 for flag in ("--auto-confirm","--auto-approve","--generate-patch","--apply","--force","--shell","--command","--network","--install-model"):assert flag not in text
