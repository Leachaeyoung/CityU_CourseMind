"""Evidence-first specialist agents.

These are deterministic tool-facing specialists. A future LLM wrapper may
translate their results into natural language, but it cannot bypass evidence.
"""
from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from .contracts import EvidenceRequirement
from .evidence import EvidenceItem, retrieve_official_evidence
from app.domain.rules import check_prerequisites
from app.domain.models import normalize_course_code
from app.storage.database import CourseOfferingRow, CourseRow, SourceDocumentRow


@dataclass(frozen=True)
class SpecialistResult:
    agent: str
    allowed: bool
    evidence: tuple[EvidenceItem, ...]
    blocker: Optional[str] = None
    facts: Mapping[str, Any] = field(default_factory=dict)


class CourseInfoAgent:
    name = "course_info"

    def run(self, session: Session, query: str, catalogue_year: Optional[str] = None) -> SpecialistResult:
        evidence = tuple(retrieve_official_evidence(session, query, EvidenceRequirement.OFFICIAL_COURSE, catalogue_year=catalogue_year))
        codes = {normalize_course_code(code.replace(" ", "")) for code in re.findall(r"(?:DSC|SDSC|CS)\s*\d{4,5}", query.upper())}
        rows = list(session.scalars(select(CourseRow).where(CourseRow.code.in_(codes)))) if codes else []
        if catalogue_year:
            rows = [row for row in rows if row.catalogue_year == catalogue_year]
        facts = {
            "courses": [
                {"course_code": row.code, "title": row.title, "credits": row.credits,
                 "subject": row.subject, "catalogue_year": row.catalogue_year,
                 "prerequisite": row.prerequisite_json, "official_url": row.official_url}
                for row in rows
            ]
        }
        return SpecialistResult(self.name, bool(evidence), evidence,
                                None if evidence else "没有检索到已核验的官方课程证据", facts)


class ScheduleWorkloadAgent:
    name = "schedule_workload"

    def run(self, session: Session, query: str, term_id: str) -> SpecialistResult:
        evidence = tuple(retrieve_official_evidence(session, query, EvidenceRequirement.OFFICIAL_SCHEDULE, term_id=term_id))
        codes = {normalize_course_code(code.replace(" ", "")) for code in re.findall(r"(?:DSC|SDSC|CS)\s*\d{4,5}", query.upper())}
        statement = select(CourseOfferingRow).where(
            CourseOfferingRow.term_id == term_id,
            CourseOfferingRow.source_status == "published",
        )
        if codes:
            statement = statement.where(CourseOfferingRow.course_code.in_(codes))
        rows = []
        if term_id:
            for row in session.scalars(statement):
                note = (row.access_note or "").lower()
                majors = {item.upper() for item in (row.allowed_majors or [])}
                # CourseMind serves DSC/DSE/DSE1 majors only. Exclude minor,
                # other-programme, and unrelated-major-only sections.
                if "minor" in note or "only for programme" in note:
                    continue
                if majors and not majors.intersection({"DSC", "DSE", "DSE1"}):
                    continue
                rows.append(row)
        facts = {"term_id": term_id, "registration_status_confirmed": False,
                 "notice": "课表详情请以 AIMS 系统实际显示为准。",
                 "offerings": [{
                     "course_code": row.course_code, "section": row.section, "crn": row.crn,
                     "credit_units": row.credit_units, "slots": row.slots,
                     "date_start": row.date_start, "date_end": row.date_end,
                     "building": row.building, "room": row.room, "instructor": row.instructor,
                     "medium": row.medium, "allowed_majors": row.allowed_majors,
                     "allowed_programmes": row.allowed_programmes, "access_note": row.access_note,
                     "is_snapshot": row.is_snapshot,
                 } for row in rows]}
        return SpecialistResult(self.name, bool(evidence), evidence,
                                None if evidence else "没有检索到该学期已发布的 AIMS 课表证据", facts)


class AcademicRulesAgent:
    name = "academic_rules"

    def run(self, session: Session, query: str, catalogue_year: str) -> SpecialistResult:
        evidence = tuple(retrieve_official_evidence(session, query, EvidenceRequirement.OFFICIAL_RULE, catalogue_year=catalogue_year))
        rule_rows = list(session.scalars(select(SourceDocumentRow).where(
            SourceDocumentRow.official.is_(True),
            SourceDocumentRow.document_type == "programme_rule",
            SourceDocumentRow.source_status == "published",
            SourceDocumentRow.catalogue_year == catalogue_year,
        ))) if catalogue_year else []
        if not rule_rows:
            # The current CityU major page may label major requirements with
            # the next effective term while GE/college requirements use the
            # current term. Keep the official rule as fallback evidence.
            rule_rows = list(session.scalars(select(SourceDocumentRow).where(
                SourceDocumentRow.official.is_(True),
                SourceDocumentRow.document_type == "programme_rule",
                SourceDocumentRow.source_status == "published",
            )))
        facts = {"rules": [
            {"title": row.title, "catalogue_year": row.catalogue_year,
             "source_url": row.source_url, "verified_at": row.verified_at,
             "excerpt": row.content[:500]}
            for row in rule_rows
        ]}
        return SpecialistResult(self.name, bool(evidence), evidence,
                                None if evidence else "没有检索到该 catalogue year 的官方培养方案证据", facts)


class PlannerAgent:
    name = "planner"

    def run(self, session: Session, query: str, term_id: str, catalogue_year: Optional[str] = None) -> SpecialistResult:
        # Planner is not allowed to synthesize a recommendation before both
        # schedule and course evidence exist.
        schedule = retrieve_official_evidence(session, query, EvidenceRequirement.OFFICIAL_SCHEDULE, term_id=term_id)
        course = retrieve_official_evidence(session, query, EvidenceRequirement.OFFICIAL_COURSE, catalogue_year=catalogue_year)
        evidence = tuple(schedule + course)
        allowed = bool(schedule and course)
        facts = {
            "term_id": term_id,
            "catalogue_year": catalogue_year,
            "hard_constraints": ["prerequisites", "major_track", "section_eligibility", "schedule_conflicts", "credit_audit"],
            "evidence_ready": {"official_schedule": bool(schedule), "official_course": bool(course)},
            "seat_availability_used": False,
        }
        return SpecialistResult(self.name, allowed, evidence,
                                None if allowed else "规划需要同时具备 AIMS 课表证据和官方课程证据", facts)
