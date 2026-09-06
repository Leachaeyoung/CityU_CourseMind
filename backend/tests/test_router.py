from app.agents.contracts import AgentType, EvidenceRequirement, Intent
from app.agents.router import route_request


def test_course_fact_forces_official_course_evidence():
    route = route_request("DSC4070 的先修课和课程内容是什么？")
    assert route.intent == Intent.COURSE_FACT
    assert route.primary_agent == AgentType.COURSE_INFO
    assert route.evidence_requirement == EvidenceRequirement.OFFICIAL_COURSE


def test_schedule_planning_requires_published_official_schedule_evidence():
    route = route_request("帮我排下学期课表，不能时间冲突")
    assert route.intent == Intent.SCHEDULE_PLAN
    assert route.primary_agent == AgentType.SCHEDULE_WORKLOAD
    assert route.evidence_requirement == EvidenceRequirement.OFFICIAL_SCHEDULE
    assert AgentType.ACADEMIC_RULES in route.supporting_agents


def test_general_chitchat_does_not_force_rag():
    route = route_request("你好，你能做什么？")
    assert route.intent == Intent.CLARIFICATION
    assert route.evidence_requirement == EvidenceRequirement.NONE


def test_official_grading_breakdown_is_course_fact_not_community_review():
    route = route_request("CS2334 的评分标准和考试比例是什么？")
    assert route.intent == Intent.COURSE_FACT
    assert route.evidence_requirement == EvidenceRequirement.OFFICIAL_COURSE
