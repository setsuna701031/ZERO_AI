from __future__ import annotations

"""Architecture contract for the engineering task stack.

The stack has one owner per concern. Cross-layer calls are allowed only when
they delegate to that owner; state mutation stays with the owner module.
"""

ENGINEERING_STACK_CONTRACT_SCHEMA = "zero.engineering_stack.contract.v1"


OWNERS = {
    "planning": "core.tasks.engineering_planning_loop.EngineeringPlanningLoop",
    "lifecycle": "core.tasks.engineering_goal_lifecycle.EngineeringGoalLifecycle",
    "evaluation": "core.tasks.adaptive_planning_evaluator.AdaptivePlanningEvaluator",
    "continuation": "core.tasks.goal_continuation_coordinator.GoalContinuationCoordinator",
    "execution": "core.tasks.engineering_task_runner",
    "memory": "core.tasks.engineering_memory_store.EngineeringMemoryStore",
    "dispatch": "core.agent.agent_loop.AgentLoop",
}


ALLOWED = {
    "core.tasks.adaptive_planning_evaluator": [
        "Own deterministic evaluation of latest execution and lifecycle signals.",
        "Return decision-only adaptive planning records: continue, replan, block, or complete.",
        "Use already-provided goal state, task buckets, latest result, and memory summaries as inputs.",
    ],
    "core.tasks.engineering_planning_loop": [
        "Own initial planning and replan orchestration for engineering goals.",
        "Call Planner.plan for task bucket planning.",
        "Call AdaptivePlanningEvaluator after continuation results.",
        "Ask EngineeringGoalLifecycle to create or update lifecycle state.",
        "Ask GoalContinuationCoordinator to continue planned goals.",
        "Read relevant memory through EngineeringMemoryStore.",
        "Build planning payloads and return planning evidence.",
    ],
    "core.tasks.engineering_goal_lifecycle": [
        "Own goal lifecycle state files and task buckets.",
        "Create, select, update, and finish lifecycle records.",
        "Persist lifecycle events, progress, terminal states, and memory refs.",
    ],
    "core.tasks.goal_continuation_coordinator": [
        "Own continuation loops over active lifecycle-enabled goals.",
        "Load active lifecycle state snapshots for continuation decisions.",
        "Delegate each cycle to EngineeringTaskRunner.",
        "Stop when the lifecycle owner reports a terminal goal state.",
    ],
    "core.tasks.engineering_task_runner": [
        "Own execution packaging and result bundles.",
        "Normalize executable work-package payloads through the existing planner normalizer.",
        "Execute only through WorkPackageScheduler and the existing AER path.",
        "Request memory reads and writes from EngineeringMemoryStore.",
        "Request lifecycle transitions from EngineeringGoalLifecycle for lifecycle-enabled payloads.",
    ],
    "core.tasks.engineering_memory_store": [
        "Own deterministic persistence and retrieval of engineering execution memory.",
        "Save memory records produced from result bundles.",
        "Load relevant memory by keyword and goal similarity.",
    ],
    "core.agent.agent_loop": [
        "Dispatch engineering task JSON payloads to EngineeringTaskRunner.",
        "Shape caller-visible route, plan, execution, and final response envelopes.",
    ],
}


FORBIDDEN = {
    "core.tasks.adaptive_planning_evaluator": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Generate plans or call Planner.",
        "Own lifecycle state or write lifecycle files.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Dispatch through agent_loop.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
    ],
    "core.tasks.engineering_planning_loop": [
        "Execute work packages or call run_engineering_task directly.",
        "Own memory persistence or save memory records.",
        "Own lifecycle file writes or mutate lifecycle state outside EngineeringGoalLifecycle.",
    ],
    "core.tasks.engineering_goal_lifecycle": [
        "Plan, replan, or call Planner.",
        "Execute work packages or call EngineeringTaskRunner.",
        "Own memory retrieval or persistence beyond recording memory references.",
        "Continue goals by looping over task execution.",
    ],
    "core.tasks.goal_continuation_coordinator": [
        "Plan or replan task buckets.",
        "Call Planner or EngineeringPlanningLoop.",
        "Own memory retrieval or persistence.",
        "Execute work packages directly.",
        "Own lifecycle transitions beyond reading terminal state.",
    ],
    "core.tasks.engineering_task_runner": [
        "Own engineering goal planning or call Planner.plan.",
        "Own replan authority for task buckets.",
        "Own lifecycle persistence outside EngineeringGoalLifecycle.",
        "Bypass WorkPackageScheduler for repository mutation.",
    ],
    "core.tasks.engineering_memory_store": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Plan or replan task buckets.",
        "Continue active goals or call GoalContinuationCoordinator.",
        "Own lifecycle state.",
    ],
    "core.agent.agent_loop": [
        "Plan, continue, execute, or persist engineering stack state itself.",
        "Import EngineeringGoalLifecycle, EngineeringMemoryStore, or GoalContinuationCoordinator.",
        "Bypass EngineeringTaskRunner for engineering_task JSON payloads.",
    ],
}


QUESTION_OWNERS = {
    "Who owns planning?": OWNERS["planning"],
    "Who owns lifecycle?": OWNERS["lifecycle"],
    "Who owns evaluation?": OWNERS["evaluation"],
    "Who owns continuation?": OWNERS["continuation"],
    "Who owns execution?": OWNERS["execution"],
    "Who owns memory?": OWNERS["memory"],
}


__all__ = [
    "ALLOWED",
    "ENGINEERING_STACK_CONTRACT_SCHEMA",
    "FORBIDDEN",
    "OWNERS",
    "QUESTION_OWNERS",
]
