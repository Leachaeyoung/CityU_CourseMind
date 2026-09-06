"""Contracts shared by routing, evidence retrieval, and specialist agents."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class Intent(str, Enum):
    COURSE_FACT = "course_fact"
    COURSE_COMPARE = "course_compare"
    DEGREE_AUDIT = "degree_audit"
    SCHEDULE_PLAN = "schedule_plan"
    PERSONALIZED_PLAN = "personalized_plan"
    COMMUNITY_DISCUSSION = "community_discussion"
    CLARIFICATION = "clarification"


class AgentType(str, Enum):
    COURSE_INFO = "course_info"
    ACADEMIC_RULES = "academic_rules"
    SCHEDULE_WORKLOAD = "schedule_workload"
    PLANNER = "planner"


class EvidenceRequirement(str, Enum):
    NONE = "none"
    OFFICIAL_COURSE = "official_course"
    OFFICIAL_RULE = "official_rule"
    OFFICIAL_SCHEDULE = "official_schedule"
    OFFICIAL_AND_COMMUNITY = "official_and_community"


@dataclass(frozen=True)
class RoutingDecision:
    """A deterministic, explainable route for one user request.

    V1 deliberately has one instance per specialist. Agent health can make an
    instance unavailable, but it must never reroute a rules request to an
    unrelated specialist just because that specialist is faster.
    """

    intent: Intent
    primary_agent: AgentType | None
    supporting_agents: Tuple[AgentType, ...]
    evidence_requirement: EvidenceRequirement
    reason: str
    needs_profile: bool = False
