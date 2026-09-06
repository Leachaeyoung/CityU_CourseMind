from app.agents.specialists import AcademicRulesAgent, CourseInfoAgent, ScheduleWorkloadAgent
from app.storage.database import CourseOfferingRow, CourseRow, SourceDocumentRow, build_session_factory


def test_course_info_agent_cannot_answer_without_official_evidence():
    session = build_session_factory("sqlite://")()
    result = CourseInfoAgent().run(session, "DSC4070 课程内容")
    assert result.allowed is False
    assert result.blocker


def test_schedule_agent_uses_term_scoped_official_evidence():
    session = build_session_factory("sqlite://")()
    session.add(SourceDocumentRow(
        document_type="schedule", title="AIMS 2026-A", content="DSC3006 section C01 timetable",
        official=True, source_url="aims://2026-A", term_id="2026-A", source_status="published", verified_at="now",
    ))
    session.commit()
    result = ScheduleWorkloadAgent().run(session, "DSC3006 section", "2026-A")
    assert result.allowed is True
    assert result.evidence[0].term_id == "2026-A"


def test_schedule_agent_returns_snapshot_facts_without_seat_fields():
    session = build_session_factory("sqlite://")()
    session.add(SourceDocumentRow(
        document_type="schedule", title="AIMS 2026-A", content="DSC3006 C01 timetable",
        official=True, source_url="aims://2026-A", term_id="2026-A", source_status="published", verified_at="now",
    ))
    session.add(CourseOfferingRow(
        course_code="DSC3006", term_id="2026-A", section="C01", slots=[{"weekday": 2, "start_minute": 900, "end_minute": 1070}],
        source_status="published", source_url="aims://2026-A", verified_at="now", crn="12140",
        building="CMC", room="M3017", instructor="ZENG Li", is_snapshot=True,
        available_seats=45, capacity=150, waitlist_available=30,
    ))
    session.commit()
    result = ScheduleWorkloadAgent().run(session, "SDSC3006 上课时间", "2026-A")
    assert result.allowed is True
    assert result.facts["offerings"][0]["crn"] == "12140"
    assert result.facts["registration_status_confirmed"] is False
    assert "available_seats" not in result.facts["offerings"][0]


def test_course_info_agent_returns_structured_facts_for_legacy_code_query():
    session = build_session_factory("sqlite://")()
    session.add(CourseRow(
        code="DSC3006", title="Fundamentals of Machine Learning I", credits=3,
        subject="DSC", offering_academic_unit="Data Science", catalogue_year="2026/27",
        official_url="https://cityu.example/DSC3006", prerequisite_json={"required_any_groups": [["MA2506", "MA2510"]]},
    ))
    session.add(SourceDocumentRow(
        document_type="course", title="DSC3006 official", content="DSC3006 official course facts",
        official=True, source_url="https://cityu.example/DSC3006", catalogue_year="2026/27",
        course_code="DSC3006", source_status="published", verified_at="now",
    ))
    session.commit()
    result = CourseInfoAgent().run(session, "SDSC3006 的先修课", catalogue_year="2026/27")
    assert result.allowed is True
    assert result.facts["courses"][0]["course_code"] == "DSC3006"


def test_academic_rules_agent_returns_catalogue_year_scoped_rule_facts():
    session = build_session_factory("sqlite://")()
    session.add(SourceDocumentRow(
        document_type="programme_rule", title="BSc Data Science 2026/27",
        content="121 credit units required; major requirements are versioned by catalogue year.",
        official=True, source_url="https://cityu.example/dsc-major", catalogue_year="2026/27",
        source_status="published", verified_at="now",
    ))
    session.commit()
    result = AcademicRulesAgent().run(session, "BSc Data Science catalogue year credit requirements", "2026/27")
    assert result.allowed is True
    assert result.facts["rules"][0]["catalogue_year"] == "2026/27"
