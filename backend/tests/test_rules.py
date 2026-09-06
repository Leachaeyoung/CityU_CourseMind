from app.domain.models import (
    Course,
    CourseOffering,
    CourseRecord,
    CourseStatus,
    DegreeRequirement,
    MeetingSlot,
    PrerequisiteRule,
    StudentProfile,
    TermStatus,
)
from app.domain.rules import (
    audit_degree_requirement,
    calculate_credits,
    check_prerequisites,
    check_minimum_major_credits,
    check_schedule_conflicts,
    check_section_eligibility,
)


def profile(*passed_codes):
    return StudentProfile(
        user_id="student-1",
        programme="SDSC",
        catalogue_year="2024-25",
        completed_courses=[CourseRecord(code, CourseStatus.PASSED) for code in passed_codes],
    )


def course(code, credits=3, prerequisite=None):
    return Course(
        code=code,
        title="Test course " + code,
        credits=credits,
        subject="DSC",
        catalogue_year="2024-25",
        prerequisite=prerequisite or PrerequisiteRule(),
        official_url="https://example.invalid/" + code,
    )


def test_sdsc_profile_and_course_code_are_normalized_to_current_dsc():
    student = profile("SDSC1001")
    assert student.programme == "DSC"
    assert student.completed_courses[0].course_code == "DSC1001"


def test_dse1_is_a_distinct_major_track():
    student = StudentProfile(user_id="student-1", programme="DSC", catalogue_year="2024-25", major_track="DSE1")
    assert student.major_track == "DSE1"


def test_section_eligibility_accepts_dse1_for_dse_and_rejects_dsc():
    offering = CourseOffering("DSC3008", "2026-A", "C01", (), TermStatus.PUBLISHED, allowed_majors=("DSE",))
    dse1 = StudentProfile(user_id="dse1", programme="DSC", catalogue_year="2024-25", major_track="DSE1")
    dsc = StudentProfile(user_id="dsc", programme="DSC", catalogue_year="2024-25", major_track="DSC")
    assert check_section_eligibility(dse1, offering)[0] is True
    assert check_section_eligibility(dsc, offering)[0] is False


def test_prerequisite_requires_all_and_one_option_from_each_group():
    target = course(
        "DSC4000",
        prerequisite=PrerequisiteRule(
            required_all=("DSC1001",),
            required_any_groups=(("CS1001", "DSC1002"),),
            source_url="https://example.invalid/catalogue",
            catalogue_year="2024-25",
        ),
    )

    result = check_prerequisites(target, profile("DSC1001"))
    assert result.eligible is False
    assert result.missing_required == ()
    assert result.missing_any_groups == (("CS1001", "DSC1002"),)

    assert check_prerequisites(target, profile("DSC1001", "CS1001")).eligible is True


def test_capstone_minimum_major_credit_threshold_supports_dse1_exception():
    capstone = Course("DSC4116", "Capstone", 6, "DSC", "2026/27", minimum_major_credits=30)
    catalog = {"DSC1001": course("DSC1001", credits=3), "DSC2001": course("DSC2001", credits=3)}
    assert check_minimum_major_credits(capstone, profile("DSC1001", "DSC2001"), catalog).eligible is False
    dse_catalog = {f"DSC10{i}": course(f"DSC10{i}", credits=3) for i in range(1, 9)}
    dse1 = StudentProfile(user_id="dse1", programme="DSC", catalogue_year="2024-25", major_track="DSE1",
                          completed_courses=[CourseRecord(code, CourseStatus.PASSED) for code in dse_catalog])
    assert check_minimum_major_credits(capstone, dse1, dse_catalog).eligible is True


def test_credit_calculation_rejects_unknown_courses_and_deduplicates_codes():
    courses = {"DSC1001": course("DSC1001"), "CS1001": course("CS1001", credits=4)}
    assert calculate_credits(["DSC1001", "dsc1001", "CS1001"], courses) == 7

    try:
        calculate_credits(["UNKNOWN"], courses)
    except ValueError as error:
        assert "UNKNOWN" in str(error)
    else:
        raise AssertionError("unknown courses must not be silently ignored")


def test_schedule_conflicts_only_use_published_offerings():
    first = CourseOffering(
        "DSC1001", "2026-A", "A", (MeetingSlot(1, 9 * 60, 10 * 60 + 30),), TermStatus.PUBLISHED
    )
    second = CourseOffering(
        "CS1001", "2026-A", "B", (MeetingSlot(1, 10 * 60, 11 * 60),), TermStatus.PUBLISHED
    )
    conflicts = check_schedule_conflicts([first, second])
    assert len(conflicts) == 1
    assert conflicts[0].overlap_start == 10 * 60
    assert conflicts[0].overlap_end == 10 * 60 + 30

    unpublished = CourseOffering(
        "CS1001", "2026-B", "B", (MeetingSlot(1, 10 * 60, 11 * 60),), TermStatus.UNAVAILABLE
    )
    try:
        check_schedule_conflicts([first, unpublished])
    except ValueError as error:
        assert "different terms" in str(error)
    else:
        raise AssertionError("different terms must not be compared")


def test_degree_audit_uses_profile_catalogue_year_and_passed_courses_only():
    courses = {
        "DSC1001": course("DSC1001"),
        "CS1001": course("CS1001"),
        "DSC2001": course("DSC2001"),
    }
    requirement = DegreeRequirement(
        catalogue_year="2024-25",
        required_credits=9,
        required_courses=("DSC1001", "DSC2001"),
        elective_groups=(("CS1001", "DSC2001"),),
    )
    result = audit_degree_requirement(profile("DSC1001", "CS1001"), requirement, courses)
    assert result.completed_credits == 6
    assert result.missing_required_courses == ("DSC2001",)
    assert result.unsatisfied_elective_groups == ()
    assert result.meets_credit_requirement is False
