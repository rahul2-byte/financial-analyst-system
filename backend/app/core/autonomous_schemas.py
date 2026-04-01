from __future__ import annotations

from enum import Enum


class TaskPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CriticDecision(str, Enum):
    APPROVE = "approve"
    RETRY = "retry"
    CONFLICT = "conflict"
    INSUFFICIENT_DATA = "insufficient_data"


class RouterDecision(str, Enum):
    RUN_GOAL_HYPOTHESIS = "run_goal_hypothesis"
    RUN_DATA_CHECK = "run_data_check"
    RUN_DATA_PLAN = "run_data_plan"
    RUN_DATA_FETCH = "run_data_fetch"
    RUN_RESEARCH_PLAN = "run_research_plan"
    RUN_RESEARCH_EXEC = "run_research_exec"
    RUN_SYNTHESIS = "run_synthesis"
    RUN_CRITIC = "run_critic"
    RUN_REFLECTION = "run_reflection"
    RUN_CONFLICT_RESOLUTION = "run_conflict_resolution"
    RUN_VALIDATION = "run_validation"
    TERMINATE_SUCCESS = "terminate_success"
    TERMINATE_INSUFFICIENT_DATA = "terminate_insufficient_data"
    TERMINATE_BUDGET_EXCEEDED = "terminate_budget_exceeded"
    TERMINATE_FAILURE = "terminate_failure"
