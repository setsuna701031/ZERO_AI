from __future__ import annotations

"""Architecture contract for the engineering task stack.

The stack has one owner per concern. Cross-layer calls are allowed only when
they delegate to that owner; state mutation stays with the owner module.
"""

ENGINEERING_STACK_CONTRACT_SCHEMA = "zero.engineering_stack.contract.v1"


OWNERS = {
    "dependencies": "core.tasks.engineering_goal_dependency_graph.EngineeringGoalDependencyGraph",
    "scheduler": "core.tasks.engineering_goal_scheduler.EngineeringGoalScheduler",
    "portfolio": "core.tasks.engineering_goal_portfolio.EngineeringGoalPortfolio",
    "planning": "core.tasks.engineering_planning_loop.EngineeringPlanningLoop",
    "lifecycle": "core.tasks.engineering_goal_lifecycle.EngineeringGoalLifecycle",
    "evaluation": "core.tasks.adaptive_planning_evaluator.AdaptivePlanningEvaluator",
    "runtime_orchestration": "core.tasks.engineering_runtime_orchestrator.EngineeringRuntimeOrchestrator",
    "continuation": "core.tasks.goal_continuation_coordinator.GoalContinuationCoordinator",
    "execution": "core.tasks.engineering_task_runner",
    "memory": "core.tasks.engineering_memory_store.EngineeringMemoryStore",
    "dispatch": "core.agent.agent_loop.AgentLoop",
}


ALLOWED = {
    "core.tasks.engineering_goal_dependency_graph": [
        "Own engineering goal dependency records and relationship validation.",
        "Represent parent and child goal relationships.",
        "Evaluate prerequisite goals, blocked-by goals, dependency completion, and dependency cycles.",
        "Return deterministic dependency graph status output.",
    ],
    "core.tasks.engineering_goal_scheduler": [
        "Own deterministic scheduling order and scheduling actions for engineering goals.",
        "Pause, resume, cancel, and defer goals by returning updated scheduling metadata.",
        "Ask EngineeringGoalPortfolio to select runnable goals.",
        "Route selected goals through the portfolio to an injected EngineeringPlanningLoop.",
        "Return scheduler decision records with selected_goal_id, action, reason, skipped_goals, and deferred_goals.",
    ],
    "core.tasks.adaptive_planning_evaluator": [
        "Own deterministic evaluation of latest execution and lifecycle signals.",
        "Return decision-only adaptive planning records: continue, replan, block, or complete.",
        "Use already-provided goal state, task buckets, latest result, and memory summaries as inputs.",
    ],
    "core.tasks.engineering_runtime_orchestrator": [
        "Own the engineering runtime loop only.",
        "Ask EngineeringGoalScheduler for the next runnable goal.",
        "Ask EngineeringGoalDependencyGraph to validate selected-goal dependencies.",
        "Invoke EngineeringPlanningLoop for planning orchestration.",
        "Invoke GoalContinuationCoordinator for continuation through the existing execution owner.",
        "Invoke AdaptivePlanningEvaluator and delegate evaluator-decision persistence to EngineeringGoalLifecycle.",
        "Emit structured runtime trace events with deterministic decision states.",
    ],
    "core.tasks.engineering_goal_portfolio": [
        "Own deterministic selection across multiple engineering goals.",
        "Return portfolio decision records with selected_goal_id, decision, reason, and skipped_goals.",
        "Route the selected goal payload to an injected EngineeringPlanningLoop.",
        "Skip completed, blocked, and cancelled goals.",
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
    "core.tasks.engineering_goal_dependency_graph": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Schedule goals or call EngineeringGoalScheduler.",
        "Select goals or call EngineeringGoalPortfolio.",
        "Generate plans or call Planner.",
        "Own lifecycle state or instantiate EngineeringGoalLifecycle.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
        "Dispatch through agent_loop.",
    ],
    "core.tasks.engineering_goal_scheduler": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Generate plans or call Planner.",
        "Own lifecycle state or instantiate EngineeringGoalLifecycle.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
        "Dispatch through agent_loop.",
    ],
    "core.tasks.adaptive_planning_evaluator": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Generate plans or call Planner.",
        "Own lifecycle state or write lifecycle files.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Dispatch through agent_loop.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
    ],
    "core.tasks.engineering_runtime_orchestrator": [
        "Generate plans or call Planner.",
        "Own lifecycle state or write lifecycle files.",
        "Execute work packages or call EngineeringTaskRunner.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
        "Dispatch through agent_loop.",
    ],
    "core.tasks.engineering_goal_portfolio": [
        "Execute work packages or call EngineeringTaskRunner.",
        "Generate plans or call Planner.",
        "Own lifecycle state or instantiate EngineeringGoalLifecycle.",
        "Persist memory or instantiate EngineeringMemoryStore.",
        "Call AER, WorkPackageScheduler, or work-package execution directly.",
        "Dispatch through agent_loop.",
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
    "Who owns dependencies?": OWNERS["dependencies"],
    "Who owns scheduling?": OWNERS["scheduler"],
    "Who owns multi-goal selection?": OWNERS["portfolio"],
    "Who owns planning?": OWNERS["planning"],
    "Who owns lifecycle?": OWNERS["lifecycle"],
    "Who owns evaluation?": OWNERS["evaluation"],
    "Who owns runtime orchestration?": OWNERS["runtime_orchestration"],
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
