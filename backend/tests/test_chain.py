from app.agents.chain import execute_chain
from app.storage.database import SourceDocumentRow, build_session_factory


def test_chain_routes_course_fact_to_course_info_agent():
    session = build_session_factory("sqlite://")()
    session.add(SourceDocumentRow(document_type="course", title="DSC4070", content="official course facts", official=True, source_url="cityu://4070", catalogue_year="2026/27", source_status="published", verified_at="now", course_code="DSC4070"))
    session.commit()
    result = execute_chain(session, "DSC4070 课程内容", catalogue_year="2026/27")
    assert result["primary_agent"] == "course_info"
    assert result["allowed"] is True
