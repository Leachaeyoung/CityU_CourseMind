"""Domain objects independent from databases, LLMs, and web frameworks.

The models in this module represent facts and user-provided records. They do
not infer academic eligibility: that belongs to deterministic rules.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


def normalize_program(program: str) -> str:
    """Normalize the historical programme name to the current DSC name."""
    normalized = (program or "").strip().upper()
    return "DSC" if normalized == "SDSC" else normalized


def normalize_course_code(course_code: str) -> str:
    """Normalize legacy SDSC course codes to their current DSC codes."""
    normalized = (course_code or "").strip().upper()
    return "DSC" + normalized[4:] if normalized.startswith("SDSC") else normalized


def normalize_major_track(major_track: str) -> str:
    normalized = (major_track or "").strip().upper()
    if normalized not in {"DSC", "DSE", "DSE1"}:
        raise ValueError("major_track must be DSC, DSE, or DSE1")
    return normalized


class CourseStatus(str, Enum):
    PASSED = "passed"
    IN_PROGRESS = "in_progress"
    PLANNED = "planned"


class ProgrammeCourseScope(str, Enum):
    CORE = "core"
    ELECTIVE = "elective"
    COLLEGE_SPECIFIED = "college_specified"


class TermStatus(str, Enum):
    PUBLISHED = "published"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PrerequisiteRule:
    """A course's prerequisite logic.

    ``required_all`` means every listed course must be passed. Each item in
    ``required_any_groups`` means at least one item in that group must be
    passed. The source field makes future official-rule citation possible.
    """

    required_all: Tuple[str, ...] = ()
    required_any_groups: Tuple[Tuple[str, ...], ...] = ()
    source_url: str = ""
    catalogue_year: str = ""


@dataclass(frozen=True)
class Course:
    code: str
    title: str
    credits: int
    subject: str
    catalogue_year: str
    offering_academic_unit: str = ""
    duration_terms: int = 1
    minimum_major_credits: Optional[int] = None
    prerequisite: PrerequisiteRule = field(default_factory=PrerequisiteRule)
    official_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_course_code(self.code))
        if not self.code.strip():
            raise ValueError("course code is required")
        if self.credits < 0:
            raise ValueError("course credits cannot be negative")
        if self.duration_terms <= 0:
            raise ValueError("duration_terms must be positive")


@dataclass(frozen=True)
class CourseRecord:
    course_code: str
    status: CourseStatus
    term_id: Optional[str] = None
    grade: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "course_code", normalize_course_code(self.course_code))


@dataclass
class StudentProfile:
    user_id: str
    programme: str
    catalogue_year: str
    major_track: str = "DSC"
    completed_courses: List[CourseRecord] = field(default_factory=list)
    current_courses: List[CourseRecord] = field(default_factory=list)
    max_credits: Optional[int] = None
    unavailable_slots: List["MeetingSlot"] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    workload_preference: Optional[str] = None

    def __post_init__(self) -> None:
        self.programme = normalize_program(self.programme)
        self.major_track = normalize_major_track(self.major_track)
        if self.programme != "DSC":
            raise ValueError("CourseMind V1 supports the CityU undergraduate DSC programme only")
        if not self.catalogue_year.strip():
            raise ValueError("catalogue year is required")


@dataclass(frozen=True)
class MeetingSlot:
    """A weekly time interval. weekday uses ISO numbering: Monday=1 ... Sunday=7."""

    weekday: int
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if self.weekday < 1 or self.weekday > 7:
            raise ValueError("weekday must be between 1 and 7")
        if self.start_minute < 0 or self.end_minute > 24 * 60 or self.start_minute >= self.end_minute:
            raise ValueError("meeting slot must have a valid positive interval")


@dataclass(frozen=True)
class CourseOffering:
    course_code: str
    term_id: str
    section: str
    slots: Tuple[MeetingSlot, ...]
    status: TermStatus
    source_url: str = ""
    last_verified_at: str = ""
    credit_units: Optional[int] = None  # credits attributable to this term's offering
    allowed_majors: Tuple[str, ...] = ()
    allowed_programmes: Tuple[str, ...] = ()
    access_note: str = ""
    is_snapshot: bool = False


@dataclass(frozen=True)
class CourseReview:
    """A subjective community review. It must never be treated as an official fact."""

    course_code: str
    author_id: str
    term_id: str
    overall_rating: int
    workload: str
    difficulty: str
    assessment_pressure: str
    content: str
    instructor_or_section: Optional[str] = None
    anonymous: bool = True

    def __post_init__(self) -> None:
        if self.overall_rating < 1 or self.overall_rating > 5:
            raise ValueError("overall rating must be between 1 and 5")
        if len(self.content.strip()) < 30:
            raise ValueError("review content must contain at least 30 characters")
        allowed = {"low", "medium", "high"}
        if self.workload not in allowed or self.difficulty not in allowed or self.assessment_pressure not in allowed:
            raise ValueError("review dimensions must be low, medium, or high")


@dataclass(frozen=True)
class DegreeRequirement:
    catalogue_year: str
    required_credits: int
    required_courses: Tuple[str, ...] = ()
    elective_groups: Tuple[Tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    missing_required: Tuple[str, ...]
    missing_any_groups: Tuple[Tuple[str, ...], ...]
    source_url: str
    catalogue_year: str


@dataclass(frozen=True)
class ScheduleConflict:
    first_course: str
    first_section: str
    second_course: str
    second_section: str
    weekday: int
    overlap_start: int
    overlap_end: int


@dataclass(frozen=True)
class DegreeAuditResult:
    completed_credits: int
    missing_required_courses: Tuple[str, ...]
    unsatisfied_elective_groups: Tuple[Tuple[str, ...], ...]
    meets_credit_requirement: bool
