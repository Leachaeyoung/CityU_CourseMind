"""Evidence-first specialist execution chain."""
from dataclasses import asdict
import re
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from .contracts import Intent
from .router import route_request
from .specialists import AcademicRulesAgent, CourseInfoAgent, PlannerAgent, ScheduleWorkloadAgent
from .llm_provider import synthesize_answer


def execute_chain(session: Session, message: str, catalogue_year: Optional[str] = None, term_id: Optional[str] = None, profile: Optional[Mapping] = None) -> dict:
    decision = route_request(message)
    result = None
    if decision.intent == Intent.COURSE_FACT:
        result = CourseInfoAgent().run(session, message, catalogue_year)
        # A bare course code is an overview request. Include the selected
        # term's AIMS sections as well, because the user may expect CRN/time
        # details that are not part of the Catalogue record.
        code_text = re.sub(r"(?:DSC|SDSC|CS)\s*\d{4,5}", "", message.upper())
        if term_id and not code_text.strip(" \t\r\n？！?。，,、:："):
            schedule = ScheduleWorkloadAgent().run(session, message, term_id)
            merged_facts = dict(result.facts)
            merged_facts["term_schedule"] = dict(schedule.facts)
            result = type(result)(result.agent, bool(result.evidence),
                                  tuple(list(result.evidence) + list(schedule.evidence)),
                                  result.blocker if result.evidence else schedule.blocker,
                                  merged_facts)
    elif decision.intent == Intent.DEGREE_AUDIT:
        result = AcademicRulesAgent().run(session, message, catalogue_year or "")
    elif decision.intent == Intent.SCHEDULE_PLAN:
        result = ScheduleWorkloadAgent().run(session, message, term_id or "")
        if result and profile and any(k in message.lower() for k in ("可以选吗", "能选吗", "能不能选", "选课资格", "eligibility", "eligible")):
            facts = dict(result.facts)
            facts["student_profile"] = {"major_track": profile.get("major_track"), "programme": profile.get("programme"),
                                         "completed_courses": profile.get("completed_courses", [])}
            track = str(profile.get("major_track") or "").upper()
            eligible_sections = []
            for offering in facts.get("offerings", []):
                majors = {str(item).upper() for item in (offering.get("allowed_majors") or [])}
                if not majors or track in majors or (track == "DSE1" and "DSE" in majors):
                    eligible_sections.append(offering.get("section"))
            facts["eligibility_result"] = {"major_track": track, "eligible": bool(eligible_sections),
                                            "eligible_sections": eligible_sections,
                                            "reason": "该 Section 的 Major 限制与画像分流匹配" if eligible_sections else "该课程已发布 Section 的 Major 限制与画像分流不匹配"}
            result = type(result)(result.agent, result.allowed, result.evidence, result.blocker, facts)
    elif decision.intent in {Intent.PERSONALIZED_PLAN, Intent.COURSE_COMPARE}:
        result = PlannerAgent().run(session, message, term_id or "", catalogue_year)
    response = {
        "intent": decision.intent.value,
        "primary_agent": decision.primary_agent.value if decision.primary_agent else None,
        "allowed": result.allowed if result else False,
        "blocker": result.blocker if result else "当前请求需要进一步澄清",
        "facts": dict(result.facts) if result else {},
        "evidence": [asdict(item) for item in result.evidence] if result else [],
    }
    if result:
        response.update(synthesize_answer(result.agent, message, response["evidence"], response["facts"]))
    return response
