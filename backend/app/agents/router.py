"""Transparent routing rules for CourseMind's specialist agents.

This is intentionally not an LLM router. It combines explicit UI intent (when
provided) with lightweight query signals, so each path is auditable and easy
to evaluate before an LLM is introduced for natural-language understanding.
"""
import re
from typing import Optional

from .contracts import AgentType, EvidenceRequirement, Intent, RoutingDecision


def _has_course_code(text: str) -> bool:
    return bool(re.search(r"(?:DSC|SDSC|CS)\s*\d{4,5}", text.upper()))


def route_request(message: str, requested_intent: Optional[Intent] = None) -> RoutingDecision:
    text = message.strip().lower()
    intent = requested_intent or _infer_intent(text)

    if intent == Intent.COURSE_FACT:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.COURSE_INFO,
            supporting_agents=(),
            evidence_requirement=EvidenceRequirement.OFFICIAL_COURSE,
            reason="课程内容、先修课和官方教学信息必须引用课程目录或教学大纲。",
        )
    if intent == Intent.COURSE_COMPARE:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.SCHEDULE_WORKLOAD,
            supporting_agents=(AgentType.COURSE_INFO,),
            evidence_requirement=EvidenceRequirement.OFFICIAL_AND_COMMUNITY,
            reason="比较需要先确认官方课程事实，再把社区体验作为偏好信号。",
            needs_profile=True,
        )
    if intent == Intent.DEGREE_AUDIT:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.ACADEMIC_RULES,
            supporting_agents=(),
            evidence_requirement=EvidenceRequirement.OFFICIAL_RULE,
            reason="毕业审计依赖学生 catalogue year 下的官方培养方案与已修课程。",
            needs_profile=True,
        )
    if intent == Intent.SCHEDULE_PLAN:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.SCHEDULE_WORKLOAD,
            supporting_agents=(AgentType.ACADEMIC_RULES, AgentType.PLANNER),
            evidence_requirement=EvidenceRequirement.OFFICIAL_SCHEDULE,
            reason="无冲突结论必须基于已发布学期的官方 section 时间，同时校验先修课。",
            needs_profile=True,
        )
    if intent == Intent.PERSONALIZED_PLAN:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.PLANNER,
            supporting_agents=(AgentType.ACADEMIC_RULES, AgentType.SCHEDULE_WORKLOAD),
            evidence_requirement=EvidenceRequirement.OFFICIAL_AND_COMMUNITY,
            reason="个性化方案先满足规则与开课约束，再按画像和社区信号排序。",
            needs_profile=True,
        )
    if intent == Intent.COMMUNITY_DISCUSSION:
        return RoutingDecision(
            intent=intent,
            primary_agent=AgentType.SCHEDULE_WORKLOAD,
            supporting_agents=(),
            evidence_requirement=EvidenceRequirement.NONE,
            reason="仅讨论学生体验时不把评论误当作官方事实。",
        )
    return RoutingDecision(
        intent=Intent.CLARIFICATION,
        primary_agent=None,
        supporting_agents=(),
        evidence_requirement=EvidenceRequirement.NONE,
        reason="先澄清用户想了解课程、毕业规则、还是下一学期排课。",
    )


def _infer_intent(text: str) -> Intent:
    # A specific course's credits/duration are course facts, not a degree audit.
    if any(keyword in text for keyword in ("同学评价", "学生评价", "student review", "student reviews", "students say")):
        return Intent.COMMUNITY_DISCUSSION
    if _has_course_code(text) and any(keyword in text for keyword in ("区别", "对比", "比较", "哪个", "which", "compare", "harder", "difference")):
        return Intent.COURSE_COMPARE
    if _has_course_code(text) and any(keyword in text for keyword in ("几学分", "学分是多少", "几学期", "课程内容")):
        return Intent.COURSE_FACT
    if any(keyword in text for keyword in ("毕业", "学分", "degreeworks", "培养方案", "audit", "graduation", "programme requirements", "credits missing", "缺哪些", "必修课", "必读", "核心课程", "必修有哪些", "是必修")):
        return Intent.DEGREE_AUDIT
    if any(keyword in text for keyword in ("冲突", "课表", "时间", "什么时候", "何时", "地点", "教室", "楼", "房间", "上课地点", "可以选吗", "能选吗", "能不能选", "选课资格", "section", "crn", "排课", "where", "held", "room", "class time", "timetable", "schedule", "time conflict", "eligibility", "eligible")):
        return Intent.SCHEDULE_PLAN
    if any(keyword in text for keyword in ("帮我选", "推荐", "规划", "下学期", "下一学期", "这学期", "recommend", "next semester", "plan", "choose courses", "course selection")):
        return Intent.PERSONALIZED_PLAN
    if any(keyword in text for keyword in ("评分标准", "考试比例", "评核", "assessment", "考试")):
        return Intent.COURSE_FACT
    if any(keyword in text for keyword in ("同学", "社区", "评论", "学生评价", "student review", "student reviews", "students say", "comments", "workload")):
        return Intent.COMMUNITY_DISCUSSION
    if any(keyword in text for keyword in ("区别", "对比", "比较", "哪个", "难不难", "评价", "评分", "体验", "老师", "工作量", "难度", "更适合", "哪门")):
        return Intent.COURSE_COMPARE if _has_course_code(text) else Intent.COMMUNITY_DISCUSSION
    if _has_course_code(text) or any(keyword in text for keyword in ("先修", "课程内容", "syllabus")):
        return Intent.COURSE_FACT
    return Intent.CLARIFICATION
