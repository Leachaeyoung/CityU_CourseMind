from app.agents.contracts import EvidenceRequirement
from app.agents.evidence import retrieve_official_evidence
from app.storage.database import SourceDocumentRow, build_session_factory


def test_hybrid_retriever_prioritizes_exact_course_code_and_returns_official_only():
    session = build_session_factory("sqlite://")()
    session.add_all([
        SourceDocumentRow(document_type="course", title="DSC4070", content="Large Language Models and transformers", official=True, source_url="https://example/4070", catalogue_year="2026/27", source_status="published", verified_at="now", course_code="DSC4070"),
        SourceDocumentRow(document_type="course", title="DSC3006", content="Machine learning fundamentals", official=True, source_url="https://example/3006", catalogue_year="2026/27", source_status="published", verified_at="now", course_code="DSC3006"),
        SourceDocumentRow(document_type="course", title="DSC4070 community", content="student review", official=False, source_url="https://example/review", catalogue_year="2026/27", source_status="published", verified_at="now", course_code="DSC4070"),
    ])
    session.commit()
    results = retrieve_official_evidence(session, "DSC4070 course content", EvidenceRequirement.OFFICIAL_COURSE)
    assert results[0].source_url.endswith("4070")
    assert all(item.source_url != "https://example/review" for item in results)
