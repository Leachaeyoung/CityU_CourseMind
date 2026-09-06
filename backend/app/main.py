"""CourseMind HTTP API.

This first API slice exposes the structured "My" profile and the course-review
community. Agent orchestration is intentionally added after these source facts
and community constraints are reliable.
"""
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.contracts import EvidenceRequirement, Intent
from app.agents.evidence import retrieve_official_evidence
from app.agents.chain import execute_chain
from app.agents.planner import rank_candidates
from app.agents.router import route_request
from app.domain.models import Course, CourseOffering, CourseRecord, CourseReview, CourseStatus, MeetingSlot, PrerequisiteRule, StudentProfile, TermStatus, normalize_course_code
from app.domain.rules import calculate_credits, check_minimum_major_credits, check_prerequisites, check_schedule_conflicts, filter_courses_for_programme
from app.storage.database import CourseOfferingRow, CourseReviewRow, CourseRow, ProgrammeCourseScopeRow, SourceDocumentRow, StudentCourseRow, StudentProfileRow, build_session_factory, session_dependency


class MeetingSlotInput(BaseModel):
    weekday: int = Field(ge=1, le=7)
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)


class CourseRecordInput(BaseModel):
    course_code: str = Field(min_length=3, max_length=32)
    status: CourseStatus
    term_id: Optional[str] = Field(default=None, max_length=32)
    grade: Optional[str] = Field(default=None, max_length=16)


class ProfileUpsertInput(BaseModel):
    programme: str
    major_track: str = Field(default="DSC", pattern="^(DSC|DSE|DSE1)$")
    catalogue_year: str = Field(min_length=3, max_length=32)
    completed_courses: List[CourseRecordInput] = Field(default_factory=list)
    current_courses: List[CourseRecordInput] = Field(default_factory=list)
    max_credits: Optional[int] = Field(default=None, ge=1, le=30)
    unavailable_slots: List[MeetingSlotInput] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    workload_preference: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")


class CourseCreateInput(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    title: str = Field(min_length=1, max_length=256)
    credits: int = Field(ge=1, le=30)
    subject: str = Field(pattern="^(DSC|CS)$")
    offering_academic_unit: str = Field(default="", max_length=128)
    duration_terms: int = Field(default=1, ge=1, le=4)
    minimum_major_credits: Optional[int] = Field(default=None, ge=0, le=200)
    catalogue_year: str = Field(min_length=3, max_length=32)
    official_url: str = Field(default="", max_length=1024)
    required_all: List[str] = Field(default_factory=list)
    required_any_groups: List[List[str]] = Field(default_factory=list)


class ReviewCreateInput(BaseModel):
    author_id: str = Field(min_length=1, max_length=80)
    term_id: str = Field(min_length=1, max_length=32)
    overall_rating: int = Field(ge=1, le=5)
    workload: str = Field(pattern="^(low|medium|high)$")
    difficulty: str = Field(pattern="^(low|medium|high)$")
    assessment_pressure: str = Field(pattern="^(low|medium|high)$")
    content: str = Field(min_length=30, max_length=3000)
    instructor_or_section: Optional[str] = Field(default=None, max_length=120)
    anonymous: bool = True


class SourceDocumentCreateInput(BaseModel):
    document_type: str = Field(pattern="^(course|programme_rule|schedule|syllabus)$")
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=200000)
    source_url: str = Field(min_length=1, max_length=1024)
    catalogue_year: Optional[str] = Field(default=None, max_length=32)
    term_id: Optional[str] = Field(default=None, max_length=32)
    source_status: str = Field(default="published", pattern="^(published|stale|unavailable)$")
    course_code: Optional[str] = Field(default=None, max_length=32)
    verified_at: Optional[str] = Field(default=None, max_length=40)


class ChatRouteInput(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    user_id: Optional[str] = Field(default=None, max_length=80)
    requested_intent: Optional[Intent] = None
    term_id: Optional[str] = Field(default=None, max_length=32)


class OfferingCreateInput(BaseModel):
    course_code: str = Field(min_length=3, max_length=32)
    term_id: str = Field(min_length=1, max_length=32)
    section: str = Field(min_length=1, max_length=32)
    slots: List[MeetingSlotInput] = Field(min_length=1)
    source_status: TermStatus
    source_url: str = Field(min_length=1, max_length=1024)
    verified_at: Optional[str] = Field(default=None, max_length=40)
    credit_units: Optional[int] = Field(default=None, ge=1, le=30)
    allowed_majors: List[str] = Field(default_factory=list, max_length=16)
    allowed_programmes: List[str] = Field(default_factory=list, max_length=16)
    access_note: str = Field(default="", max_length=500)


class OfferingSelectionInput(BaseModel):
    course_code: str = Field(min_length=3, max_length=32)
    section: str = Field(min_length=1, max_length=32)


class PlanPreflightInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    term_id: str = Field(min_length=1, max_length=32)
    selections: List[OfferingSelectionInput] = Field(min_length=1, max_length=10)


class ProgrammeScopeInput(BaseModel):
    programme: str = Field(min_length=1, max_length=16)
    catalogue_year: str = Field(min_length=3, max_length=32)
    course_code: str = Field(min_length=3, max_length=32)
    scope: str = Field(pattern="^(core|elective|college_specified)$")
    source_url: str = Field(min_length=1, max_length=1024)


def _profile_response(profile: StudentProfileRow) -> dict:
    records = [
        {
            "course_code": record.course_code,
            "status": record.status,
            "term_id": record.term_id,
            "grade": record.grade,
        }
        for record in profile.course_records
    ]
    return {
        "user_id": profile.user_id,
        "programme": profile.programme,
        "catalogue_year": profile.catalogue_year,
        "major_track": profile.major_track,
        "completed_courses": [r for r in records if r["status"] == CourseStatus.PASSED.value],
        "current_courses": [r for r in records if r["status"] == CourseStatus.IN_PROGRESS.value],
        "max_credits": profile.max_credits,
        "unavailable_slots": profile.unavailable_slots or [],
        "interests": profile.interests or [],
        "workload_preference": profile.workload_preference,
    }


def _domain_profile(profile: StudentProfileRow) -> StudentProfile:
    records = [CourseRecord(record.course_code, CourseStatus(record.status), record.term_id, record.grade) for record in profile.course_records]
    return StudentProfile(
        user_id=profile.user_id,
        programme=profile.programme,
        catalogue_year=profile.catalogue_year,
        major_track=profile.major_track,
        completed_courses=[record for record in records if record.status == CourseStatus.PASSED],
        current_courses=[record for record in records if record.status == CourseStatus.IN_PROGRESS],
        max_credits=profile.max_credits,
        unavailable_slots=[MeetingSlot(**slot) for slot in profile.unavailable_slots or []],
        interests=profile.interests or [],
        workload_preference=profile.workload_preference,
    )


def _domain_course(row: CourseRow) -> Course:
    prerequisite = row.prerequisite_json or {}
    return Course(
        code=row.code,
        title=row.title,
        credits=row.credits,
        subject=row.subject,
        catalogue_year=row.catalogue_year,
        offering_academic_unit=row.offering_academic_unit,
        duration_terms=row.duration_terms,
        minimum_major_credits=row.minimum_major_credits,
        official_url=row.official_url,
        prerequisite=PrerequisiteRule(
            required_all=tuple(prerequisite.get("required_all", [])),
            required_any_groups=tuple(tuple(group) for group in prerequisite.get("required_any_groups", [])),
            source_url=row.official_url,
            catalogue_year=row.catalogue_year,
        ),
    )


def _domain_offering(row: CourseOfferingRow) -> CourseOffering:
    return CourseOffering(
        course_code=row.course_code,
        term_id=row.term_id,
        section=row.section,
        slots=tuple(MeetingSlot(**slot) for slot in row.slots),
        status=TermStatus(row.source_status),
        source_url=row.source_url,
        last_verified_at=row.verified_at,
        credit_units=row.credit_units,
        allowed_majors=tuple(row.allowed_majors or []),
        allowed_programmes=tuple(row.allowed_programmes or []),
        access_note=row.access_note,
        is_snapshot=row.is_snapshot,
    )


def create_app(database_url: Optional[str] = None) -> FastAPI:
    default_db = Path(__file__).resolve().parents[1] / "coursemind.db"
    url = database_url or os.getenv("COURSEMIND_DATABASE_URL", f"sqlite:///{default_db}")
    session_factory = build_session_factory(url)
    app = FastAPI(title="CourseMind", version="0.1.0")
    # Allow the same local UI to be opened either through /app/ or directly as
    # a file:// URL during development. No credentials are accepted by these
    # endpoints, so wildcard CORS is limited to this local prototype.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    app.state.metrics = {"requests_total": 0, "errors_total": 0, "evidence_requests": 0,
                         "evidence_hits": 0, "latency_ms_total": 0.0}

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):
        started = time.perf_counter()
        metrics = request.app.state.metrics
        metrics["requests_total"] += 1
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                metrics["errors_total"] += 1
            return response
        except Exception:
            metrics["errors_total"] += 1
            raise
        finally:
            metrics["latency_ms_total"] += (time.perf_counter() - started) * 1000

    def get_session():
        yield from session_dependency(session_factory)

    @app.get("/", include_in_schema=False)
    def app_home() -> RedirectResponse:
        return RedirectResponse(url="/app/", status_code=307)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "coursemind"}

    @app.get("/metrics")
    def metrics(session: Session = Depends(get_session)) -> dict:
        """Expose lightweight local metrics; no student content is included."""
        values = dict(app.state.metrics)
        values["average_latency_ms"] = round(values["latency_ms_total"] / values["requests_total"], 2) if values["requests_total"] else 0.0
        values["evidence_hit_rate"] = round(values["evidence_hits"] / values["evidence_requests"], 4) if values["evidence_requests"] else None
        latest = session.scalar(select(func.max(CourseOfferingRow.verified_at)).where(CourseOfferingRow.is_snapshot.is_(True)))
        return {"service": "coursemind", "metrics": values, "aims_snapshot_latest_verified_at": latest}

    @app.put("/profiles/{user_id}")
    def upsert_profile(user_id: str, body: ProfileUpsertInput, session: Session = Depends(get_session)) -> dict:
        try:
            domain_profile = StudentProfile(
                user_id=user_id,
                programme=body.programme,
                catalogue_year=body.catalogue_year,
                major_track=body.major_track,
                completed_courses=[CourseRecord(**record.model_dump()) for record in body.completed_courses],
                current_courses=[CourseRecord(**record.model_dump()) for record in body.current_courses],
                max_credits=body.max_credits,
                unavailable_slots=[MeetingSlot(**slot.model_dump()) for slot in body.unavailable_slots],
                interests=body.interests,
                workload_preference=body.workload_preference,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

        profile = session.get(StudentProfileRow, user_id)
        if profile is None:
            profile = StudentProfileRow(user_id=user_id, programme=domain_profile.programme, major_track=domain_profile.major_track, catalogue_year=body.catalogue_year)
            session.add(profile)

        profile.programme = domain_profile.programme
        profile.major_track = domain_profile.major_track
        profile.catalogue_year = body.catalogue_year
        profile.max_credits = body.max_credits
        profile.unavailable_slots = [slot.model_dump() for slot in body.unavailable_slots]
        profile.interests = [interest.strip() for interest in body.interests if interest.strip()]
        profile.workload_preference = body.workload_preference
        profile.course_records.clear()
        all_records = body.completed_courses + body.current_courses
        profile.course_records.extend(
            StudentCourseRow(
                course_code=normalize_course_code(record.course_code),
                status=record.status.value,
                term_id=record.term_id,
                grade=record.grade,
            )
            for record in all_records
        )
        session.commit()
        session.refresh(profile)
        return _profile_response(profile)

    @app.get("/profiles/{user_id}")
    def get_profile(user_id: str, session: Session = Depends(get_session)) -> dict:
        profile = session.get(StudentProfileRow, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="profile not found")
        return _profile_response(profile)

    @app.get("/profiles/{user_id}/progress")
    def profile_progress(user_id: str, session: Session = Depends(get_session)) -> dict:
        """Return a friendly graduation-progress summary for the My page."""
        profile = session.get(StudentProfileRow, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="profile not found")
        passed = {record.course_code.upper() for record in profile.course_records
                  if record.status == CourseStatus.PASSED.value}
        courses = {row.code: row for row in session.scalars(select(CourseRow))}
        completed = sorted(code for code in passed if code in courses)
        completed_credits = sum(courses[code].credits for code in completed)
        scope_rows = list(session.scalars(select(ProgrammeCourseScopeRow).where(
            ProgrammeCourseScopeRow.programme == profile.programme,
            ProgrammeCourseScopeRow.catalogue_year == profile.catalogue_year,
        )))
        if not scope_rows:
            scope_rows = list(session.scalars(select(ProgrammeCourseScopeRow).where(
                ProgrammeCourseScopeRow.programme == profile.programme,
                ProgrammeCourseScopeRow.catalogue_year == "2027/28",
            )))
        # The normative page marks DSC3001/DSC3025/DSC3026 as ACT-stream-only
        # core choices; for the regular DSC profile they are electives or not
        # required, so they must not appear as graduation gaps.
        act_only = {"DSC3001", "DSC3025", "DSC3026"}
        core_codes = sorted({row.course_code for row in scope_rows
                             if row.scope == "core" and row.course_code not in act_only})
        missing_core = [code for code in core_codes if code not in passed]
        college_codes = ["CS1315", "DSC2003", "CS3402"]
        school_codes = ["MA1503", "MA1508"]
        missing_college = [code for code in college_codes if code not in passed and code in courses]
        missing_school = [code for code in school_codes if code not in passed and code in courses]
        ge_codes = ["GE1401", "GE2401", "GE1501", "GE1601"]
        missing_ge = [code for code in ge_codes if code not in passed and code in courses]
        elective_codes = {row.course_code for row in scope_rows if row.scope == "elective"}
        elective_credits = sum(courses[code].credits for code in passed if code in elective_codes and code in courses)
        return {
            "user_id": user_id,
            "catalogue_year": profile.catalogue_year,
            "major_track": profile.major_track,
            "completed_courses": [{"course_code": code, "title": courses[code].title, "credits": courses[code].credits} for code in completed],
            "completed_credits": completed_credits,
            "graduation_credits": 121,
            "remaining_credits": max(121 - completed_credits, 0),
            "major_requirement_range": "64–67 学分（按培养方案分流）",
            "missing_core_courses": [{"course_code": code, "title": courses[code].title, "credits": courses[code].credits} for code in missing_core if code in courses],
            "requirements": {
                "ge": {"target_credits": 31, "missing_named_courses": [{"course_code": code, "title": courses[code].title, "credits": courses[code].credits} for code in missing_ge]},
                "college_specified": {"target_credits": 9, "missing_courses": [{"course_code": code, "title": courses[code].title, "credits": courses[code].credits} for code in missing_college]},
                "college_school": {"target_credits": 8, "missing_courses": [{"course_code": code, "title": courses[code].title, "credits": courses[code].credits} for code in missing_school]},
                "major_electives": {"target_credits": 21, "completed_credits": elective_credits, "remaining_credits": max(21 - elective_credits, 0)},
            },
        }

    @app.post("/admin/courses", status_code=status.HTTP_201_CREATED)
    def upsert_course(body: CourseCreateInput, session: Session = Depends(get_session)) -> dict:
        try:
            course = Course(
                code=body.code.strip().upper(),
                title=body.title.strip(),
                credits=body.credits,
                subject=body.subject,
                catalogue_year=body.catalogue_year,
                offering_academic_unit=body.offering_academic_unit,
                duration_terms=body.duration_terms,
                minimum_major_credits=body.minimum_major_credits,
                official_url=body.official_url,
                prerequisite=PrerequisiteRule(
                    required_all=tuple(code.strip().upper() for code in body.required_all),
                    required_any_groups=tuple(
                        tuple(code.strip().upper() for code in group) for group in body.required_any_groups
                    ),
                    source_url=body.official_url,
                    catalogue_year=body.catalogue_year,
                ),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

        row = session.get(CourseRow, course.code)
        if row is None:
            row = CourseRow(code=course.code, title=course.title, credits=course.credits, subject=course.subject, catalogue_year=course.catalogue_year, offering_academic_unit=course.offering_academic_unit)
            session.add(row)
        row.title = course.title
        row.credits = course.credits
        row.subject = course.subject
        row.offering_academic_unit = course.offering_academic_unit
        row.duration_terms = course.duration_terms
        row.minimum_major_credits = course.minimum_major_credits
        row.catalogue_year = course.catalogue_year
        row.official_url = course.official_url
        row.prerequisite_json = {
            "required_all": list(course.prerequisite.required_all),
            "required_any_groups": [list(group) for group in course.prerequisite.required_any_groups],
        }
        session.commit()
        return {"code": row.code, "title": row.title, "catalogue_year": row.catalogue_year}

    @app.post("/admin/source-documents", status_code=status.HTTP_201_CREATED)
    def create_source_document(body: SourceDocumentCreateInput, session: Session = Depends(get_session)) -> dict:
        """Ingest reviewed official source text with explicit provenance.

        This endpoint is intentionally administrative: an end user cannot make
        arbitrary web text appear as an official answer source.
        """
        row = SourceDocumentRow(
            document_type=body.document_type,
            title=body.title.strip(),
            content=body.content.strip(),
            official=True,
            source_url=body.source_url.strip(),
            catalogue_year=body.catalogue_year,
            term_id=body.term_id,
            source_status=body.source_status,
            course_code=body.course_code.strip().upper() if body.course_code else None,
            verified_at=body.verified_at or datetime.now(timezone.utc).isoformat(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"source_id": row.id, "document_type": row.document_type, "source_status": row.source_status}

    @app.post("/admin/offerings", status_code=status.HTTP_201_CREATED)
    def upsert_offering(body: OfferingCreateInput, session: Session = Depends(get_session)) -> dict:
        course_code = body.course_code.strip().upper()
        if session.get(CourseRow, course_code) is None:
            raise HTTPException(status_code=404, detail="course must be imported before its offering")
        try:
            offering = CourseOffering(
                course_code=course_code,
                term_id=body.term_id,
                section=body.section.strip().upper(),
                slots=tuple(MeetingSlot(**slot.model_dump()) for slot in body.slots),
                status=body.source_status,
                source_url=body.source_url,
                last_verified_at=body.verified_at or datetime.now(timezone.utc).isoformat(),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        row = session.scalar(
            select(CourseOfferingRow).where(
                CourseOfferingRow.course_code == offering.course_code,
                CourseOfferingRow.term_id == offering.term_id,
                CourseOfferingRow.section == offering.section,
            )
        )
        if row is None:
            row = CourseOfferingRow(
                course_code=offering.course_code,
                term_id=offering.term_id,
                section=offering.section,
                slots=[],
                source_status=offering.status.value,
                source_url=offering.source_url,
                verified_at=offering.last_verified_at,
                credit_units=body.credit_units,
                allowed_majors=[],
                allowed_programmes=[],
                access_note="",
            )
            session.add(row)
        row.slots = [slot.model_dump() for slot in body.slots]
        row.source_status = offering.status.value
        row.source_url = offering.source_url
        row.verified_at = offering.last_verified_at
        row.credit_units = body.credit_units
        row.allowed_majors = [item.strip().upper() for item in body.allowed_majors if item.strip()]
        row.allowed_programmes = [item.strip().upper() for item in body.allowed_programmes if item.strip()]
        row.access_note = body.access_note.strip()
        session.commit()
        return {"course_code": row.course_code, "term_id": row.term_id, "section": row.section, "source_status": row.source_status}

    @app.post("/admin/programme-course-scopes", status_code=status.HTTP_201_CREATED)
    def upsert_programme_scope(body: ProgrammeScopeInput, session: Session = Depends(get_session)) -> dict:
        course_code = body.course_code.strip().upper()
        if session.get(CourseRow, course_code) is None:
            raise HTTPException(status_code=404, detail="course must be imported before assigning programme scope")
        row = session.scalar(
            select(ProgrammeCourseScopeRow).where(
                ProgrammeCourseScopeRow.programme == body.programme.strip().upper(),
                ProgrammeCourseScopeRow.catalogue_year == body.catalogue_year,
                ProgrammeCourseScopeRow.course_code == course_code,
            )
        )
        if row is None:
            row = ProgrammeCourseScopeRow(
                programme=body.programme.strip().upper(),
                catalogue_year=body.catalogue_year,
                course_code=course_code,
                scope=body.scope,
                source_url=body.source_url,
            )
            session.add(row)
        else:
            row.scope = body.scope
            row.source_url = body.source_url
        session.commit()
        return {"programme": row.programme, "catalogue_year": row.catalogue_year, "course_code": row.course_code, "scope": row.scope}

    @app.post("/planning/preflight")
    def planning_preflight(body: PlanPreflightInput, session: Session = Depends(get_session)) -> dict:
        """Evaluate hard constraints for an explicitly selected next-term plan.

        It reports evidence and blockers, but it does not perform registration
        and it does not claim eligibility when the source schedule is stale.
        """
        profile_row = session.get(StudentProfileRow, body.user_id)
        if profile_row is None:
            raise HTTPException(status_code=404, detail="profile not found")
        profile = _domain_profile(profile_row)
        selected_offerings = []
        selected_courses = {}
        blockers = []
        seen_course_codes = set()
        for selection in body.selections:
            course_code = selection.course_code.strip().upper()
            section = selection.section.strip().upper()
            if course_code in seen_course_codes:
                blockers.append(f"{course_code} appears more than once in the plan")
                continue
            seen_course_codes.add(course_code)
            offering_row = session.scalar(
                select(CourseOfferingRow).where(
                    CourseOfferingRow.course_code == course_code,
                    CourseOfferingRow.term_id == body.term_id,
                    CourseOfferingRow.section == section,
                )
            )
            course_row = session.get(CourseRow, course_code)
            if offering_row is None or course_row is None:
                blockers.append(f"official offering not found for {course_code} section {section} in {body.term_id}")
                continue
            if "minor" in (offering_row.access_note or "").lower():
                blockers.append(f"{course_code} section {section} is a minor-only offering and is excluded from CourseMind major planning")
                continue
            selected_offerings.append(_domain_offering(offering_row))
            selected_courses[course_code] = _domain_course(course_row)

            allowed_majors = {item.upper() for item in offering_row.allowed_majors}
            major_matches = profile.major_track in allowed_majors or (profile.major_track == "DSE1" and "DSE" in allowed_majors)
            if allowed_majors and not major_matches:
                blockers.append(f"{course_code} section {section} is restricted to other majors")
            if offering_row.allowed_programmes and profile.programme not in {item.upper() for item in offering_row.allowed_programmes}:
                blockers.append(f"{course_code} section {section} is restricted to other programmes")

        scope_rows = list(session.scalars(select(ProgrammeCourseScopeRow).where(
            ProgrammeCourseScopeRow.programme == profile.programme,
            ProgrammeCourseScopeRow.catalogue_year == profile.catalogue_year,
        )))
        permitted_scopes = {
            (row.programme, row.catalogue_year, row.course_code)
            for row in scope_rows
        }
        if not scope_rows:
            blockers.append("DSC programme course scope is not imported for this catalogue year")
        else:
            _, out_of_scope = filter_courses_for_programme(
                selected_courses.keys(), profile.programme, profile.catalogue_year, permitted_scopes
            )
            if out_of_scope:
                blockers.append("outside the official DSC programme course scope: " + ", ".join(sorted(out_of_scope)))

        eligibility = {
            code: {
                "eligible": result.eligible,
                "missing_required": list(result.missing_required),
                "missing_any_groups": [list(group) for group in result.missing_any_groups],
                "source_url": result.source_url,
                "catalogue_year": result.catalogue_year,
            }
            for code, course in selected_courses.items()
            for result in [check_prerequisites(course, profile)]
        }
        course_catalog = {row.code: _domain_course(row) for row in session.scalars(select(CourseRow))}
        for code, course in selected_courses.items():
            minimum = check_minimum_major_credits(course, profile, course_catalog)
            if not minimum.eligible:
                eligibility[code]["eligible"] = False
                eligibility[code]["missing_required"] += list(minimum.missing_required)
        if any(not result["eligible"] for result in eligibility.values()):
            blockers.append("one or more selected courses have unsatisfied official prerequisites")
        if len(selected_offerings) != len(body.selections) or any(
            offering.status != TermStatus.PUBLISHED for offering in selected_offerings
        ):
            blockers.append("all selected sections need published official schedule data before conflict verification")
            conflicts = []
        else:
            conflicts = [conflict.__dict__ for conflict in check_schedule_conflicts(selected_offerings)]
            if conflicts:
                blockers.append("selected sections have timetable conflicts")
        credits = calculate_credits(selected_courses.keys(), selected_courses) if selected_courses else 0
        if profile.max_credits is not None and credits > profile.max_credits:
            blockers.append(f"selected credits ({credits}) exceed your configured limit ({profile.max_credits})")
        return {
            "term_id": body.term_id,
            "selected_credits": credits,
            "credit_limit": profile.max_credits,
            "registration_status_confirmed": bool(selected_offerings) and all(not offering.is_snapshot for offering in selected_offerings),
            "prerequisite_checks": eligibility,
            "schedule_conflicts": conflicts,
            "official_schedule_sources": [
                {"course_code": offering.course_code, "section": offering.section, "source_url": offering.source_url, "verified_at": offering.last_verified_at}
                for offering in selected_offerings
            ],
            "hard_constraints_passed": not blockers,
            "blockers": blockers,
            "notice": "时间冲突结果可用于 Semester A 2026/27 规划；当前座位和可注册状态未确认。" if any(offering.is_snapshot for offering in selected_offerings) else "",
        }

    @app.get("/planning/candidates")
    def planning_candidates(user_id: str, term_id: str, session: Session = Depends(get_session)) -> dict:
        """List courses the saved profile can currently consider.

        This is a deterministic candidate filter, not an LLM recommendation:
        AIMS eligibility and published sections are applied before ranking.
        """
        profile_row = session.get(StudentProfileRow, user_id)
        if profile_row is None:
            raise HTTPException(status_code=404, detail="profile not found")
        profile = _domain_profile(profile_row)
        scope_rows = list(session.scalars(select(ProgrammeCourseScopeRow).where(
            ProgrammeCourseScopeRow.programme == profile.programme,
            ProgrammeCourseScopeRow.catalogue_year == profile.catalogue_year,
        )))
        permitted = {row.course_code for row in scope_rows}
        rows = list(session.scalars(select(CourseOfferingRow).where(
            CourseOfferingRow.term_id == term_id,
            CourseOfferingRow.source_status == "published",
        )))
        candidates = []
        excluded = []
        for code in sorted({row.course_code for row in rows}):
            course_row = session.get(CourseRow, code)
            if course_row is None:
                continue
            if permitted and code not in permitted:
                excluded.append({"course_code": code, "reason": "outside programme scope"})
                continue
            course = _domain_course(course_row)
            prereq = check_prerequisites(course, profile)
            minimum = check_minimum_major_credits(course, profile, {item.code: _domain_course(item) for item in session.scalars(select(CourseRow))})
            sections = []
            for row in [item for item in rows if item.course_code == code and (item.credit_units or 0) > 0
                        and "minor" not in (item.access_note or "").lower()]:
                majors = {item.upper() for item in (row.allowed_majors or [])}
                major_ok = not majors or profile.major_track in majors or (profile.major_track == "DSE1" and "DSE" in majors)
                programme_ok = not row.allowed_programmes or profile.programme in {item.upper() for item in row.allowed_programmes}
                if major_ok and programme_ok:
                    sections.append({"section": row.section, "crn": row.crn, "credit_units": row.credit_units,
                                     "slots": row.slots,
                                     "access_note": row.access_note})
            if not sections:
                excluded.append({"course_code": code, "reason": "AIMS section restriction"})
                continue
            candidates.append({"course_code": code, "title": course_row.title, "credits": course_row.credits,
                               "prerequisite": {"eligible": prereq.eligible and minimum.eligible, "missing_required": list(prereq.missing_required) + list(minimum.missing_required),
                                                 "missing_any_groups": [list(group) for group in prereq.missing_any_groups],
                                                 "source_url": prereq.source_url},
                               "sections": sections})
        return {"user_id": user_id, "term_id": term_id, "candidates": candidates,
                "ranked_candidates": rank_candidates(candidates, profile.interests), "excluded": excluded,
                "notice": "AIMS is authoritative for Semester A 2026/27 planning section eligibility; this snapshot does not confirm current registration availability."}

    @app.post("/chat/route")
    def route_chat(body: ChatRouteInput, session: Session = Depends(get_session)) -> dict:
        """Run the safe part of the Agent chain before LLM answer synthesis.

        The returned evidence is a contract for the future response generator:
        it may summarize it, but it cannot cite or invent a different official
        basis for course, rule, or schedule decisions.
        """
        decision = route_request(body.message, body.requested_intent)
        profile = session.get(StudentProfileRow, body.user_id) if body.user_id else None
        catalogue_year = profile.catalogue_year if profile else None
        evidence = retrieve_official_evidence(
            session=session,
            query=body.message,
            requirement=decision.evidence_requirement,
            catalogue_year=catalogue_year,
            term_id=body.term_id,
        ) if decision.evidence_requirement != EvidenceRequirement.NONE else []
        if decision.evidence_requirement != EvidenceRequirement.NONE:
            app.state.metrics["evidence_requests"] += 1
            if evidence:
                app.state.metrics["evidence_hits"] += 1
        blockers = []
        if decision.needs_profile and profile is None:
            blockers.append("请先在“我的”中补全 catalogue year、已修课程与偏好，系统才可做个人化规划。")
        if decision.evidence_requirement == EvidenceRequirement.OFFICIAL_SCHEDULE and not body.term_id:
            blockers.append("请指定已发布开课信息的目标学期；未发布学期不能验证时间冲突。")
        if decision.evidence_requirement != EvidenceRequirement.NONE and not evidence:
            blockers.append("当前没有可用的官方证据；请先导入或核验对应课程/规则/课表来源。")
        return {
            "routing": {
                "intent": decision.intent.value,
                "primary_agent": decision.primary_agent.value if decision.primary_agent else None,
                "supporting_agents": [agent.value for agent in decision.supporting_agents],
                "evidence_requirement": decision.evidence_requirement.value,
                "reason": decision.reason,
            },
            "profile_found": profile is not None,
            "blockers": blockers,
            "official_evidence": [item.__dict__ for item in evidence],
            "answer_generation_allowed": not blockers,
        }

    @app.post("/chat/execute")
    def execute_chat(body: ChatRouteInput, session: Session = Depends(get_session)) -> dict:
        """Run the evidence-first specialist chain before natural-language synthesis."""
        profile = session.get(StudentProfileRow, body.user_id) if body.user_id else None
        return execute_chain(session, body.message,
                             catalogue_year=profile.catalogue_year if profile else "2026/27",
                             term_id=body.term_id,
                             profile=_profile_response(profile) if profile else None)

    @app.post("/consultation/context")
    def consultation_context(body: ChatRouteInput, session: Session = Depends(get_session)) -> dict:
        """Build the read-only context consumed by the consultation UI."""
        profile = session.get(StudentProfileRow, body.user_id) if body.user_id else None
        chain = execute_chain(
            session, body.message,
            catalogue_year=profile.catalogue_year if profile else "2026/27",
            term_id=body.term_id,
            profile=_profile_response(profile) if profile else None,
        )
        return {
            "message": body.message,
            "user_id": body.user_id,
            "term_id": body.term_id,
            "profile_found": profile is not None,
            "profile": _profile_response(profile) if profile else None,
            "chain": chain,
            "read_only": True,
            "notice": "咨询结果仅提供课程规划建议，不执行 AIMS 注册或任何账户设置操作。",
        }

    @app.get("/courses")
    def list_courses(session: Session = Depends(get_session)) -> dict:
        """List the full official DSC-major curriculum for community cards.

        Supporting MA/CS/GE/IS/LT/COM courses are included as catalogue
        entries; their Semester A section fields remain empty unless an AIMS
        offering has been imported.
        """
        scoped_codes = set(session.scalars(select(ProgrammeCourseScopeRow.course_code).where(
            ProgrammeCourseScopeRow.programme == "DSC",
            ProgrammeCourseScopeRow.catalogue_year.in_(["2026/27", "2027/28"]),
        )))
        rows = list(session.scalars(select(CourseRow).where(CourseRow.code.in_(scoped_codes)).order_by(CourseRow.code)))
        return {"courses": [{"course_code": row.code, "title": row.title, "credits": row.credits,
                              "catalogue_year": row.catalogue_year} for row in rows]}

    @app.get("/courses/{course_code}/details")
    def course_details(course_code: str, term_id: Optional[str] = None, session: Session = Depends(get_session)) -> dict:
        """Return one course's official facts plus AIMS registration facts.

        AIMS is intentionally labelled as the source of truth for the selected
        term's live sections; Catalogue/source documents describe the course.
        """
        code = normalize_course_code(course_code)
        course = session.get(CourseRow, code)
        if course is None:
            raise HTTPException(status_code=404, detail="course not found")
        docs = list(session.scalars(select(SourceDocumentRow).where(
            SourceDocumentRow.course_code == code,
            SourceDocumentRow.official.is_(True),
            SourceDocumentRow.source_status == "published",
        )))
        statement = select(CourseOfferingRow).where(
            CourseOfferingRow.course_code == code,
            CourseOfferingRow.source_status == "published",
        )
        if term_id:
            statement = statement.where(CourseOfferingRow.term_id == term_id)
        offerings = [row for row in session.scalars(statement)
                     if "minor" not in (row.access_note or "").lower()
                     and "only for programme" not in (row.access_note or "").lower()
                     and (not row.allowed_majors or {item.upper() for item in row.allowed_majors}.intersection({"DSC", "DSE", "DSE1"}))]
        reviews = list(session.scalars(select(CourseReviewRow).where(CourseReviewRow.course_code == code)))
        dimension = lambda field: round(sum({"low": 1, "medium": 2, "high": 3}[getattr(item, field)] for item in reviews) / len(reviews), 2) if reviews else None
        return {
            "course": {"code": course.code, "title": course.title, "credits": course.credits,
                       "subject": course.subject, "offering_academic_unit": course.offering_academic_unit,
                       "duration_terms": course.duration_terms, "catalogue_year": course.catalogue_year,
                       "official_url": course.official_url, "prerequisite": course.prerequisite_json},
            "catalogue_evidence": [{"title": doc.title, "source_url": doc.source_url,
                                    "catalogue_year": doc.catalogue_year, "term_id": doc.term_id,
                                    "verified_at": doc.verified_at, "content": doc.content} for doc in docs],
            "aims_is_authoritative_for_term": True,
            "registration_status_confirmed": any(not row.is_snapshot for row in offerings),
            "community": {"review_count": len(reviews),
                          "average_rating": round(sum(item.overall_rating for item in reviews) / len(reviews), 2) if reviews else None,
                          "average_workload": dimension("workload"), "average_difficulty": dimension("difficulty"),
                          "average_assessment_pressure": dimension("assessment_pressure")},
            "aims_offerings": [{"term_id": row.term_id, "section": row.section, "crn": row.crn,
                                "credit_units": row.credit_units, "component_type": row.component_type,
                                "campus": row.campus, "web_enabled": row.web_enabled,
                                "date_start": row.date_start,
                                "date_end": row.date_end, "slots": row.slots, "building": row.building,
                                "room": row.room, "instructor": row.instructor, "medium": row.medium,
                                "allowed_majors": row.allowed_majors, "allowed_programmes": row.allowed_programmes,
                                "access_note": row.access_note, "source_url": row.source_url,
                                "verified_at": row.verified_at, "is_snapshot": row.is_snapshot} for row in offerings],
            "notice": "AIMS overrides Catalogue for Semester A 2026/27 term facts; this imported published schedule snapshot does not confirm current registration availability."
        }

    @app.post("/courses/{course_code}/reviews", status_code=status.HTTP_201_CREATED)
    def create_review(course_code: str, body: ReviewCreateInput, session: Session = Depends(get_session)) -> dict:
        course_code = normalize_course_code(course_code)
        if session.get(CourseRow, course_code) is None:
            raise HTTPException(status_code=404, detail="course not found")
        try:
            review = CourseReview(course_code=course_code, **body.model_dump())
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        row = CourseReviewRow(**review.__dict__)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"review_id": row.id, "course_code": row.course_code, "anonymous": row.anonymous}

    @app.get("/courses/{course_code}/reviews")
    def list_reviews(course_code: str, limit: int = 50, offset: int = 0, session: Session = Depends(get_session)) -> dict:
        course_code = normalize_course_code(course_code)
        if limit < 1 or limit > 100 or offset < 0:
            raise HTTPException(status_code=422, detail="limit must be 1..100 and offset must be non-negative")
        if session.get(CourseRow, course_code) is None:
            raise HTTPException(status_code=404, detail="course not found")
        all_reviews = list(session.scalars(select(CourseReviewRow).where(CourseReviewRow.course_code == course_code)))
        reviews = all_reviews[offset:offset + limit]
        rating_distribution = Counter(review.overall_rating for review in all_reviews)
        average_rating = round(sum(review.overall_rating for review in all_reviews) / len(all_reviews), 2) if all_reviews else None
        dimension_average = lambda field: round(sum({"low": 1, "medium": 2, "high": 3}[getattr(item, field)] for item in all_reviews) / len(all_reviews), 2) if all_reviews else None
        return {
            "course_code": course_code,
            "review_count": len(all_reviews),
            "total_review_count": len(all_reviews),
            "offset": offset,
            "limit": limit,
            "returned_count": len(reviews),
            "average_rating": average_rating,
            "average_workload": dimension_average("workload"),
            "average_difficulty": dimension_average("difficulty"),
            "average_assessment_pressure": dimension_average("assessment_pressure"),
            "rating_distribution": {str(rating): rating_distribution.get(rating, 0) for rating in range(1, 6)},
            "reviews": [
                {
                    "review_id": review.id,
                    "author": "anonymous" if review.anonymous else review.author_id,
                    "term_id": review.term_id,
                    "overall_rating": review.overall_rating,
                    "workload": review.workload,
                    "difficulty": review.difficulty,
                    "assessment_pressure": review.assessment_pressure,
                    "content": review.content,
                    "instructor_or_section": review.instructor_or_section,
                }
                for review in reviews
            ],
            "notice": "Community reviews are subjective experience signals and do not replace official course information or academic rules.",
        }

    @app.get("/courses/compare")
    def compare_courses(codes: str, session: Session = Depends(get_session)) -> dict:
        """Compare official facts and community signals for comma-separated codes."""
        requested = [normalize_course_code(code) for code in codes.split(",") if code.strip()]
        if not requested or len(requested) > 6:
            raise HTTPException(status_code=422, detail="provide 1 to 6 course codes")
        result = []
        for code in dict.fromkeys(requested):
            course = session.get(CourseRow, code)
            if course is None:
                continue
            reviews = list(session.scalars(select(CourseReviewRow).where(CourseReviewRow.course_code == code)))
            result.append({
                "course_code": code, "title": course.title, "credits": course.credits,
                "prerequisite": course.prerequisite_json, "official_url": course.official_url,
                "community": {
                    "review_count": len(reviews),
                    "average_rating": round(sum(item.overall_rating for item in reviews) / len(reviews), 2) if reviews else None,
                    "average_workload": round(sum({"low": 1, "medium": 2, "high": 3}[item.workload] for item in reviews) / len(reviews), 2) if reviews else None,
                    "average_difficulty": round(sum({"low": 1, "medium": 2, "high": 3}[item.difficulty] for item in reviews) / len(reviews), 2) if reviews else None,
                    "average_assessment_pressure": round(sum({"low": 1, "medium": 2, "high": 3}[item.assessment_pressure] for item in reviews) / len(reviews), 2) if reviews else None,
                },
            })
        found = {item["course_code"] for item in result}
        return {
            "requested_codes": list(dict.fromkeys(requested)),
            "not_found": [code for code in dict.fromkeys(requested) if code not in found],
            "dimensions": ["credits", "prerequisite", "average_rating", "average_workload", "average_difficulty", "average_assessment_pressure"],
            "courses": result,
            "comparison_basis": {"official": ["credits", "prerequisite", "official_url"], "community": ["rating", "workload", "difficulty", "assessment_pressure"]},
            "notice": "Community signals are subjective and cannot override official prerequisites, eligibility, or schedule rules.",
        }

    return app


app = create_app()
