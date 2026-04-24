from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Callable

from core.capabilities.demo_flows import (
    run_doc_demo,
    run_execution_demo,
    run_requirement_demo,
)
from core.capabilities.full_build_flow import run_full_build_demo, run_mini_build_demo
from core.persona.loader import PersonaProfile, load_default_persona
from core.persona.panel_renderer import render_persona_panel
from core.persona.state_manager import get_persona_state_manager
from core.persona.visual_profile import load_default_visual_profile
from core.persona.persona_agent_orchestrator import run_persona_agent_demo


@dataclass
class PersonaTurnResult:
    user_input: str
    response: str
    should_exit: bool


EXIT_COMMANDS = {"exit", "quit", "bye"}


def build_persona_system_prompt(persona: PersonaProfile) -> str:
    behavior_text = "\n".join(f"- {item}" for item in persona.behavior_rules)
    return (
        f"Name: {persona.name}\n"
        f"Role: {persona.role}\n"
        f"Identity: {persona.identity}\n"
        f"Tone: {persona.style.get('tone', '')}\n"
        f"Intro: {persona.intro}\n"
        f"Behavior Rules:\n{behavior_text}"
    )


def _build_help_text(persona: PersonaProfile) -> str:
    return (
        f"{persona.name}: Available persona commands:\n"
        "- help\n"
        "- status\n"
        "- panel\n"
        "- who are you\n"
        "- what can you do\n"
        "- run doc-demo\n"
        "- run multi-step-demo\n"
        "- run agent-demo\n"
        "- run requirement-demo\n"
        "- run execution-demo\n"
        "- run mini-build-demo\n"
        "- run full-build-demo\n"
        "- exit"
    )


def _extract_task_id(text: str) -> str:
    match = re.search(r"task_[0-9]+", text or "")
    return match.group(0) if match else ""


def _build_status_text(persona: PersonaProfile) -> str:
    scope = persona.capability_scope
    state_manager = get_persona_state_manager()
    visual_profile = load_default_visual_profile()
    snapshot = state_manager.get_state()
    image_path = visual_profile.resolve_image_for_state(snapshot.state)

    return (
        f"{persona.name}: Persona shell is online.\n"
        f"- current_state: {snapshot.state.value}\n"
        f"- state_reason: {snapshot.reason or '-'}\n"
        f"- state_source: {snapshot.source or '-'}\n"
        f"- state_detail: {snapshot.detail or '-'}\n"
        f"- visual_id: {visual_profile.visual_id}\n"
        f"- state_image: {image_path}\n"
        f"- last_user_command: {snapshot.last_user_command or '-'}\n"
        f"- last_capability: {snapshot.last_capability or '-'}\n"
        f"- last_result: {snapshot.last_result or '-'}\n"
        f"- last_output_hint: {snapshot.last_output_hint or '-'}\n"
        f"- last_task_id: {snapshot.last_task_id or '-'}\n"
        f"- chat: {scope.get('can_chat')}\n"
        f"- plan: {scope.get('can_plan')}\n"
        f"- explain: {scope.get('can_explain')}\n"
        f"- zero capability routing: {scope.get('can_use_zero_capabilities')}\n"
        f"- voice connected: {scope.get('can_use_voice')}\n"
        f"- avatar control connected: {scope.get('can_control_avatar')}\n"
        f"- live2d connected: {scope.get('can_use_live2d')}"
    )


def _build_panel_text() -> str:
    persona = load_default_persona()
    visual_profile = load_default_visual_profile()
    snapshot = get_persona_state_manager().get_state()
    return render_persona_panel(persona, snapshot, visual_profile)


def _output_hint_for_capability(label: str) -> str:
    hints = {
        "doc-demo": "workspace/shared/summary_demo.txt, workspace/shared/action_items_demo.txt",
        "multi-step-demo": "workspace/shared/summary_demo.txt, workspace/shared/action_items_demo.txt",
        "agent-demo": "workspace/shared/persona_agent_summary.txt, workspace/shared/persona_agent_action_items.txt",
        "requirement-demo": "workspace/shared/project_summary.txt, workspace/shared/implementation_plan.txt, workspace/shared/acceptance_checklist.txt",
        "execution-demo": "workspace/shared/hello.py",
        "mini-build-demo": "workspace/shared/number_stats.py, workspace/shared/stats_result.txt",
        "full-build-demo": "workspace/shared/project_summary.txt, workspace/shared/implementation_plan.txt, workspace/shared/acceptance_checklist.txt, workspace/shared/number_stats.py, workspace/shared/stats_result.txt",
    }
    return hints.get(label, "")


def _run_capability_capture_stdout(fn: Callable[[], int]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = fn()
    captured = buffer.getvalue()
    if captured:
        print(captured, end="" if captured.endswith("\n") else "\n")
    return code, captured


def _run_capability_with_persona_prefix(
    persona: PersonaProfile,
    label: str,
    fn: Callable[[], int],
) -> PersonaTurnResult:
    state_manager = get_persona_state_manager()
    output_hint = _output_hint_for_capability(label)

    state_manager.set_executing(
        reason=f"run_{label}",
        source="persona_chat_shell",
        detail=f"persona command triggered {label}",
        last_user_command=f"run {label}",
        last_capability=label,
        last_result="executing",
        last_output_hint=output_hint,
        last_task_id="",
    )

    print(f"{persona.name}: Starting {label}...")

    try:
        code, captured_stdout = _run_capability_capture_stdout(fn)
    except Exception as exc:
        exception_text = str(exc)
        state_manager.set_error(
            reason=f"{label}_exception",
            source="persona_chat_shell",
            detail=exception_text,
            last_user_command=f"run {label}",
            last_capability=label,
            last_result="exception",
            last_output_hint=output_hint,
            last_task_id=_extract_task_id(exception_text),
        )
        return PersonaTurnResult(
            user_input=label,
            response=f"{persona.name}: {label} failed with exception: {exc}",
            should_exit=False,
        )

    task_id = _extract_task_id(captured_stdout)

    if code == 0:
        state_manager.set_success(
            reason=f"{label}_completed",
            source="persona_chat_shell",
            detail="capability execution returned code 0",
            last_user_command=f"run {label}",
            last_capability=label,
            last_result="success",
            last_output_hint=output_hint,
            last_task_id=task_id,
        )
        return PersonaTurnResult(
            user_input=label,
            response=f"{persona.name}: {label} completed successfully.",
            should_exit=False,
        )

    state_manager.set_error(
        reason=f"{label}_failed",
        source="persona_chat_shell",
        detail=f"capability execution returned code {code}",
        last_user_command=f"run {label}",
        last_capability=label,
        last_result=f"failed:{code}",
        last_output_hint=output_hint,
        last_task_id=task_id,
    )
    return PersonaTurnResult(
        user_input=label,
        response=f"{persona.name}: {label} failed with exit code {code}.",
        should_exit=False,
    )


def generate_rule_based_response(persona: PersonaProfile, user_input: str) -> PersonaTurnResult:
    state_manager = get_persona_state_manager()

    text = (user_input or "").strip()
    lowered = text.lower()

    if lowered in EXIT_COMMANDS:
        state_manager.set_idle(
            reason="persona_exit",
            source="persona_chat_shell",
            detail="user requested shell exit",
            last_user_command=text,
        )
        return PersonaTurnResult(
            user_input=text,
            response=f"{persona.name} offline.",
            should_exit=True,
        )

    if not text:
        state_manager.set_idle(
            reason="empty_input",
            source="persona_chat_shell",
            detail="no user content received",
            last_user_command=text,
        )
        return PersonaTurnResult(
            user_input=text,
            response=f"{persona.name}: Please give me a concrete task or question.",
            should_exit=False,
        )

    if lowered == "help":
        state_manager.set_idle(
            reason="help_command",
            source="persona_chat_shell",
            detail="displayed command list",
            last_user_command=text,
        )
        return PersonaTurnResult(
            user_input=text,
            response=_build_help_text(persona),
            should_exit=False,
        )

    if lowered == "status":
        state_manager.update_runtime_summary(last_user_command=text)
        return PersonaTurnResult(
            user_input=text,
            response=_build_status_text(persona),
            should_exit=False,
        )

    if lowered == "panel":
        state_manager.update_runtime_summary(last_user_command=text)
        return PersonaTurnResult(
            user_input=text,
            response=_build_panel_text(),
            should_exit=False,
        )

    if "who are you" in lowered or "你是誰" in text:
        state_manager.set_thinking(
            reason="identity_question",
            source="persona_chat_shell",
            detail="user asked persona identity",
            last_user_command=text,
            last_result="answered_identity",
        )
        return PersonaTurnResult(
            user_input=text,
            response=f"{persona.name}: {persona.intro}",
            should_exit=False,
        )

    if "what can you do" in lowered or "你能做什麼" in text:
        state_manager.set_thinking(
            reason="capability_question",
            source="persona_chat_shell",
            detail="user asked persona capability scope",
            last_user_command=text,
            last_result="answered_capability_scope",
        )
        return PersonaTurnResult(
            user_input=text,
            response=(
                f"{persona.name}: I can help with planning, execution guidance, verification, "
                f"and selected ZERO capability routing. Voice, avatar control, and Live2D are not connected yet."
            ),
            should_exit=False,
        )

    if lowered == "run doc-demo":
        return _run_capability_with_persona_prefix(persona, "doc-demo", run_doc_demo)

    if lowered == "run multi-step-demo":
        return _run_capability_with_persona_prefix(persona, "multi-step-demo", run_doc_demo)

    if lowered == "run agent-demo":
        return _run_capability_with_persona_prefix(persona, "agent-demo", run_persona_agent_demo)

    if lowered == "run requirement-demo":
        return _run_capability_with_persona_prefix(persona, "requirement-demo", run_requirement_demo)

    if lowered == "run execution-demo":
        return _run_capability_with_persona_prefix(persona, "execution-demo", run_execution_demo)

    if lowered == "run mini-build-demo":
        return _run_capability_with_persona_prefix(persona, "mini-build-demo", run_mini_build_demo)

    if lowered == "run full-build-demo":
        return _run_capability_with_persona_prefix(persona, "full-build-demo", run_full_build_demo)

    state_manager.set_thinking(
        reason="unsupported_freeform_input",
        source="persona_chat_shell",
        detail=text,
        last_user_command=text,
        last_result="unsupported_freeform_input",
    )
    return PersonaTurnResult(
        user_input=text,
        response=(
            f"{persona.name}: Persona shell is active, but freeform LLM dialogue routing is not connected yet. "
            f"Use 'help' to see supported commands. Your input was: {text}"
        ),
        should_exit=False,
    )


def run_persona_chat_shell() -> int:
    persona = load_default_persona()
    state_manager = get_persona_state_manager()

    state_manager.set_idle(
        reason="shell_startup",
        source="persona_chat_shell",
        detail="persona shell boot completed",
        last_result="shell_ready",
    )

    print(build_persona_system_prompt(persona))
    print("")
    print(persona.greeting)
    print("Type 'help' to see commands.")
    print("Type 'exit' to leave.")
    print("")

    while True:
        try:
            user_input = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print("")
            state_manager.set_idle(
                reason="shell_interrupt",
                source="persona_chat_shell",
                detail="shell closed by eof or keyboard interrupt",
                last_result="shell_interrupted",
            )
            print(f"{persona.name} offline.")
            return 0

        result = generate_rule_based_response(persona, user_input)
        print(result.response)

        if result.should_exit:
            return 0