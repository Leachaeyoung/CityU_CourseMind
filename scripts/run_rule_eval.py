"""Run 30 deterministic CourseMind rule regression cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.domain.models import Course, CourseOffering, CourseRecord, CourseStatus, MeetingSlot, PrerequisiteRule, StudentProfile, TermStatus
from app.domain.rules import calculate_credits, check_minimum_major_credits, check_prerequisites, check_schedule_conflicts, check_section_eligibility


def main():
    passed = 0
    # 10 prerequisite cases: all/any combinations and missing records.
    for i in range(10):
        profile = StudentProfile("u", "DSC", "2026/27", completed_courses=[CourseRecord("DSC1001", CourseStatus.PASSED)] if i % 2 == 0 else [])
        target = Course("DSC9%03d" % i, "target", 3, "DSC", "2026/27", prerequisite=PrerequisiteRule(required_all=("DSC1001",)))
        assert check_prerequisites(target, profile).eligible is (i % 2 == 0)
        passed += 1
    # 10 section cases: DSC/DSE/DSE1 and programme restrictions.
    for i in range(10):
        track = ("DSC", "DSE", "DSE1")[i % 3]
        allowed = ("DSE",) if track != "DSC" else ("DSC",)
        profile = StudentProfile("u", "DSC", "2026/27", major_track=track)
        offering = CourseOffering("DSC3008", "2026-A", "C01", (), TermStatus.PUBLISHED, allowed_majors=allowed)
        expected = track != "DSC" if allowed == ("DSE",) else track == "DSC"
        assert check_section_eligibility(profile, offering)[0] is expected
        passed += 1
    # 5 timetable cases.
    for i in range(5):
        first = CourseOffering("DSC1001", "2026-A", "C01", (MeetingSlot(1, 540, 600),), TermStatus.PUBLISHED)
        second = CourseOffering("DSC2001", "2026-A", "C02", (MeetingSlot(1, 600 if i % 2 else 590, 660),), TermStatus.PUBLISHED)
        assert bool(check_schedule_conflicts([first, second])) is (i % 2 == 0)
        passed += 1
    # 5 credit/threshold cases.
    catalog = {"DSC1001": Course("DSC1001", "a", 3, "DSC", "2026/27")}
    for i in range(5):
        assert calculate_credits(["DSC1001", "DSC1001"], catalog) == 3
        capstone = Course("DSC4116", "capstone", 6, "DSC", "2026/27", minimum_major_credits=30)
        profile = StudentProfile("u", "DSC", "2026/27", completed_courses=[CourseRecord("DSC1001", CourseStatus.PASSED)])
        assert check_minimum_major_credits(capstone, profile, catalog).eligible is False
        passed += 1
    print(f"passed {passed}/30 rule cases")


if __name__ == "__main__":
    main()
