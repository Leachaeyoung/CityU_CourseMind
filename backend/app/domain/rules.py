"""Deterministic academic and scheduling rules.

These functions are intentionally independent of an LLM. A future Agent can
call them as tools, but cannot replace their conclusions with model guesses.
"""
from itertools import combinations
from typing import Dict, Iterable, List, Sequence, Set

from .models import (
    Course,
    CourseOffering,
    CourseStatus,
    DegreeAuditResult,
    DegreeRequirement,
    EligibilityResult,
    ScheduleConflict,
    StudentProfile,
    TermStatus,
)


def passed_course_codes(profile: StudentProfile) -> Set[str]:
    """Return normalized codes that the student explicitly marked as passed."""
    return {
        record.course_code.strip().upper()
        for record in profile.completed_courses
        if record.status == CourseStatus.PASSED
    }


def check_prerequisites(course: Course, profile: StudentProfile) -> EligibilityResult:
    """Evaluate prerequisite clauses against the student's formal profile."""
    passed = passed_course_codes(profile)
    required_all = tuple(code.upper() for code in course.prerequisite.required_all)
    missing_required = tuple(code for code in required_all if code not in passed)

    unsatisfied_groups = []
    for group in course.prerequisite.required_any_groups:
        normalized_group = tuple(code.upper() for code in group)
        if not any(code in passed for code in normalized_group):
            unsatisfied_groups.append(normalized_group)

    return EligibilityResult(
        eligible=not missing_required and not unsatisfied_groups,
        missing_required=missing_required,
        missing_any_groups=tuple(unsatisfied_groups),
        source_url=course.prerequisite.source_url or course.official_url,
        catalogue_year=course.prerequisite.catalogue_year or course.catalogue_year,
    )


def check_minimum_major_credits(course: Course, profile: StudentProfile, courses: Dict[str, Course]) -> EligibilityResult:
    """Check a course-level completed-major-credit threshold such as DSC4116."""
    if course.minimum_major_credits is None:
        return EligibilityResult(True, (), (), course.official_url, course.catalogue_year)
    passed = passed_course_codes(profile)
    completed = sum(courses[code].credits for code in passed if code in courses and courses[code].subject == "DSC")
    threshold = 24 if course.code == "DSC4116" and profile.major_track == "DSE1" else course.minimum_major_credits
    eligible = completed >= threshold
    return EligibilityResult(eligible, () if eligible else (f"minimum_major_credits:{threshold}",), (), course.official_url, course.catalogue_year)


def calculate_credits(course_codes: Iterable[str], courses: Dict[str, Course]) -> int:
    """Sum credits once per unique course and fail loudly for unknown codes."""
    normalized_codes = {code.strip().upper() for code in course_codes}
    unknown = sorted(code for code in normalized_codes if code not in courses)
    if unknown:
        raise ValueError("unknown course codes: " + ", ".join(unknown))
    return sum(courses[code].credits for code in normalized_codes)


def filter_courses_for_programme(
    course_codes: Iterable[str], programme: str, catalogue_year: str, permitted_scopes: Set[tuple]
) -> tuple[Set[str], Set[str]]:
    """Split requested codes into permitted and blocked programme choices.

    A department subject (for example ``CS``) is not permission to enrol. The
    programme catalogue is the authority, and an empty scope set is treated as
    missing data by the caller rather than as "everything allowed".
    """
    normalized = {code.strip().upper() for code in course_codes}
    permitted = {
        code for code in normalized
        if (programme.upper(), catalogue_year, code) in permitted_scopes
    }
    return permitted, normalized - permitted


def check_schedule_conflicts(offerings: Sequence[CourseOffering]) -> List[ScheduleConflict]:
    """Return all overlaps among offerings from the same published term."""
    conflicts: List[ScheduleConflict] = []
    for first, second in combinations(offerings, 2):
        if first.term_id != second.term_id:
            raise ValueError("cannot compare offerings from different terms")
        if first.status != TermStatus.PUBLISHED or second.status != TermStatus.PUBLISHED:
            raise ValueError("official schedule must be published before conflict checking")
        for first_slot in first.slots:
            for second_slot in second.slots:
                if first_slot.weekday != second_slot.weekday:
                    continue
                overlap_start = max(first_slot.start_minute, second_slot.start_minute)
                overlap_end = min(first_slot.end_minute, second_slot.end_minute)
                if overlap_start < overlap_end:
                    conflicts.append(
                        ScheduleConflict(
                            first_course=first.course_code,
                            first_section=first.section,
                            second_course=second.course_code,
                            second_section=second.section,
                            weekday=first_slot.weekday,
                            overlap_start=overlap_start,
                            overlap_end=overlap_end,
                        )
                    )
    return conflicts


def check_section_eligibility(profile: StudentProfile, offering: CourseOffering) -> tuple[bool, tuple[str, ...]]:
    """Check AIMS major/programme restrictions without using seat counts."""
    reasons = []
    allowed_majors = {item.upper() for item in offering.allowed_majors}
    major_matches = not allowed_majors or profile.major_track in allowed_majors or (
        profile.major_track == "DSE1" and "DSE" in allowed_majors
    )
    if not major_matches:
        reasons.append("major restriction")
    allowed_programmes = {item.upper() for item in offering.allowed_programmes}
    if allowed_programmes and profile.programme not in allowed_programmes:
        reasons.append("programme restriction")
    return not reasons, tuple(reasons)


def audit_degree_requirement(
    profile: StudentProfile,
    requirement: DegreeRequirement,
    courses: Dict[str, Course],
) -> DegreeAuditResult:
    """Audit only structured requirements for the profile's Catalogue year."""
    if profile.catalogue_year != requirement.catalogue_year:
        raise ValueError("profile and degree requirement catalogue years do not match")

    passed = passed_course_codes(profile)
    missing_required = tuple(code for code in requirement.required_courses if code.upper() not in passed)
    unsatisfied_groups = tuple(
        tuple(group)
        for group in requirement.elective_groups
        if not any(code.upper() in passed for code in group)
    )
    credits = calculate_credits(passed, courses)
    return DegreeAuditResult(
        completed_credits=credits,
        missing_required_courses=missing_required,
        unsatisfied_elective_groups=unsatisfied_groups,
        meets_credit_requirement=credits >= requirement.required_credits,
    )
