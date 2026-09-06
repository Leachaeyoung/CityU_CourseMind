"""Retrieval of auditable evidence before an agent forms a recommendation.

The initial retriever is intentionally lexical and deterministic. It is a
working, testable evidence boundary for a small V1 corpus; a hybrid vector +
keyword index can later be added behind the same contract without changing the
router or specialists.
"""
from dataclasses import dataclass
import re
import math
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import EvidenceRequirement
from app.storage.database import CourseRow, SourceDocumentRow
from app.domain.models import normalize_course_code


@dataclass(frozen=True)
class EvidenceItem:
    title: str
    source_url: str
    catalogue_year: Optional[str]
    term_id: Optional[str]
    verified_at: str
    excerpt: str
    source_type: str


def retrieve_official_evidence(
    session: Session,
    query: str,
    requirement: EvidenceRequirement,
    catalogue_year: Optional[str] = None,
    term_id: Optional[str] = None,
    limit: int = 5,
) -> List[EvidenceItem]:
    """Return only evidence safe for the requested decision type.

    Schedule requests reject stale/unavailable inputs. Other official requests
    retrieve published documents, with an optional catalogue-year filter.
    """
    statement = select(SourceDocumentRow).where(SourceDocumentRow.official.is_(True))
    if catalogue_year:
        statement = statement.where(SourceDocumentRow.catalogue_year == catalogue_year)
    if requirement == EvidenceRequirement.OFFICIAL_SCHEDULE:
        statement = statement.where(SourceDocumentRow.document_type == "schedule")
        statement = statement.where(SourceDocumentRow.source_status == "published")
        if term_id:
            statement = statement.where(SourceDocumentRow.term_id == term_id)
    else:
        statement = statement.where(SourceDocumentRow.source_status == "published")

    rows = list(session.scalars(statement))
    rows.sort(key=lambda row: _hybrid_score(row, query), reverse=True)
    result = [_to_evidence(row) for row in rows if _hybrid_score(row, query) > 0]

    # Course facts already normalized into the structured course table are also
    # valid official evidence even if no long-form source excerpt was imported.
    if requirement == EvidenceRequirement.OFFICIAL_COURSE:
        result.extend(_course_row_evidence(session, query, catalogue_year))
    return result[:limit]


def _course_row_evidence(session: Session, query: str, catalogue_year: Optional[str]) -> List[EvidenceItem]:
    codes = set(re.findall(r"(?:DSC|SDSC|CS)\s*\d{4,5}", query.upper()))
    normalized_codes = {normalize_course_code(code.replace(" ", "")) for code in codes}
    if not normalized_codes:
        return []
    rows = list(session.scalars(select(CourseRow).where(CourseRow.code.in_(normalized_codes))))
    if catalogue_year:
        rows = [row for row in rows if row.catalogue_year == catalogue_year]
    return [
        EvidenceItem(
            title=f"{row.code} — {row.title}",
            source_url=row.official_url,
            catalogue_year=row.catalogue_year,
            term_id=None,
            verified_at="structured-import",
            excerpt=f"{row.title}; {row.credits} credits; prerequisite: {row.prerequisite_json}",
            source_type="official_course_record",
        )
        for row in rows
        if row.official_url
    ]


def _score(row: SourceDocumentRow, query: str) -> int:
    haystack = f"{row.title} {row.content} {row.course_code or ''}".upper().replace("SDSC", "DSC")
    course_codes = re.findall(r"(?:DSC|SDSC|CS)\s*\d{4,5}", query.upper())
    if course_codes:
        normalized_row_code = normalize_course_code((row.course_code or "").replace(" ", "").upper())
        if any(normalize_course_code(code.replace(" ", "")) == normalized_row_code for code in course_codes):
            return 100
        if any(normalize_course_code(code.replace(" ", "")) in haystack.replace(" ", "") for code in course_codes):
            return 100
    tokens = set(re.findall(r"[A-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", query.upper()))
    return sum(token in haystack for token in tokens)


def _hybrid_score(row: SourceDocumentRow, query: str) -> float:
    """Combine exact lexical matches with a tiny dependency-free vector score."""
    lexical = _score(row, query)
    doc_tokens = re.findall(r"[A-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", f"{row.title} {row.content}".upper())
    query_tokens = re.findall(r"[A-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", query.upper())
    if not doc_tokens or not query_tokens:
        return float(lexical)
    doc_counts = {token: doc_tokens.count(token) for token in set(doc_tokens)}
    query_counts = {token: query_tokens.count(token) for token in set(query_tokens)}
    dot = sum(query_counts.get(token, 0) * count for token, count in doc_counts.items())
    norm = math.sqrt(sum(v * v for v in doc_counts.values())) * math.sqrt(sum(v * v for v in query_counts.values()))
    return lexical * 100 + (dot / norm if norm else 0.0)


def _to_evidence(row: SourceDocumentRow) -> EvidenceItem:
    return EvidenceItem(
        title=row.title,
        source_url=row.source_url,
        catalogue_year=row.catalogue_year,
        term_id=row.term_id,
        verified_at=row.verified_at,
        excerpt=row.content[:500],
        source_type=row.document_type,
    )
