from __future__ import annotations
from cli.zero_mission_runtime import parser
def test_commands_and_forbidden_flags():
    help_text=parser().format_help()
    for command in ("create","status","goals","ready","confirm-plan","advance","submit-input","cancel","evidence"):assert command in help_text
    for flag in ("--auto-confirm","--auto-approve","--force","--shell","--command","--git-commit"):assert flag not in help_text
