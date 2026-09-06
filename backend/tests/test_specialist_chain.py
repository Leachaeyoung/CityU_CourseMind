from app.agents.specialists import AcademicRulesAgent, PlannerAgent
from app.storage.database import SourceDocumentRow, build_session_factory


def test_academic_rules_agent_requires_catalogue_year_evidence():
    session = build_session_factory("sqlite://")()
    result = AcademicRulesAgent().run(session, "DSC 培养方案毕业要求", "2026/27")
    assert result.allowed is False


def test_planner_agent_requires_both_schedule_and_course_evidence():
    session = build_session_factory("sqlite://")()
    session.add_all([
        SourceDocumentRow(document_type="schedule", title="AIMS", content="DSC4070 section", official=True, source_url="aims://a", term_id="2026-A", source_status="published", verified_at="now"),
        SourceDocumentRow(document_type="course", title="DSC4070", content="course facts", official=True, source_url="cityu://dsc4070", catalogue_year="2026/27", source_status="published", verified_at="now", course_code="DSC4070"),
    ])
    session.commit()
    result = PlannerAgent().run(session, "DSC4070", "2026-A", "2026/27")
    assert result.allowed is True
    assert "schedule_conflicts" in result.facts["hard_constraints"]
    assert result.facts["seat_availability_used"] is False
