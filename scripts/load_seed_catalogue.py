"""Load the reviewed starter catalogue into a local CourseMind database.

Usage from the project root:
    backend/.venv/bin/python scripts/load_seed_catalogue.py

The operation is idempotent for the starter records and never downloads web
pages. Source text in the JSON file must have been reviewed before committing.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.storage.database import CourseRow, SourceDocumentRow, build_session_factory


def main() -> None:
    seed_path = ROOT / "data" / "seed_catalogue_2026_27.json"
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    # The programme page is the authoritative index for the full DSC major.
    # Keep its course list separate from the hand-reviewed starter facts so
    # courses that are not offered in the selected term still remain searchable
    # without inventing AIMS section data.
    curriculum_path = ROOT / "data" / "dsc_curriculum_index_2026_27.json"
    curriculum = json.loads(curriculum_path.read_text(encoding="utf-8"))
    verified_prerequisites = {
        "DSC2002": {"required_all": ["MA2508"], "required_any_groups": [["MA1503", "MA2503"]]},
        "DSC2005": {"required_all": ["DSC1001", "DSC2001"], "required_any_groups": []},
        "DSC2102": {"required_all": [], "required_any_groups": [["MA2506", "MA2510"]]},
        "DSC3004": {"required_all": ["DSC2002"], "required_any_groups": []},
        "DSC3005": {"required_all": ["DSC3007"], "required_any_groups": []},
        "DSC3010": {"required_all": ["DSC2001"], "required_any_groups": [["DSC1001"]]},
        "DSC3011": {"required_all": ["DSC2001"], "required_any_groups": [["DSC1001"]]},
        "DSC3013": {"required_all": ["DSC1001", "DSC2001"], "required_any_groups": []},
    }
    existing_codes = {item["code"] for item in payload["courses"]}
    for code, title, credits, subject, scope in curriculum["courses"]:
        if code not in existing_codes:
            payload["courses"].append({
                "code": code,
                "title": title,
                "credits": credits,
                "subject": subject,
                "offering_academic_unit": "Data Science" if subject == "DSC" else "",
                "official_url": f"https://www.cityu.edu.hk/catalogue/ug/current/course/{code}.htm",
                "required_all": verified_prerequisites.get(code, {}).get("required_all", []),
                "required_any_groups": verified_prerequisites.get(code, {}).get("required_any_groups", []),
            })
            existing_codes.add(code)
        normalized_scope = "college_specified" if scope == "college_school" else ("core" if scope.startswith("core") else ("elective" if scope != "optional" else "elective"))
        for year in ("2026/27", "2027/28"):
            payload.setdefault("programme_course_scopes", []).append({
                "programme": curriculum["programme"],
                "catalogue_year": year,
                "course_code": code,
                "scope": normalized_scope,
            })
    database_url = os.getenv("COURSEMIND_DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'coursemind.db'}")
    factory = build_session_factory(database_url)
    session = factory()
    verified_at = datetime.now(timezone.utc).isoformat()
    try:
        for item in payload["courses"]:
            row = session.get(CourseRow, item["code"])
            if row is None:
                row = CourseRow(code=item["code"], title=item["title"], credits=item["credits"], subject=item["subject"], catalogue_year=payload["catalogue_year"], offering_academic_unit=item.get("offering_academic_unit", ""), duration_terms=item.get("duration_terms", 1))
                session.add(row)
            row.title = item["title"]
            row.credits = item["credits"]
            row.subject = item["subject"]
            row.offering_academic_unit = item.get("offering_academic_unit", "")
            row.duration_terms = item.get("duration_terms", 1)
            row.minimum_major_credits = item.get("minimum_major_credits")
            row.duration_terms = item.get("duration_terms", 1)
            row.catalogue_year = payload["catalogue_year"]
            row.official_url = item["official_url"]
            row.prerequisite_json = {
                "required_all": item.get("required_all", []),
                "required_any_groups": item.get("required_any_groups", []),
            }
        source_documents = payload["source_documents"] + json.loads((ROOT / "data" / "course_sources_2026_27.json").read_text(encoding="utf-8"))
        indexed_codes = {item.get("course_code") for item in source_documents}
        for code, title, credits, _subject, _scope in curriculum["courses"]:
            if code not in indexed_codes:
                source_documents.append({
                    "document_type": "programme_course_index",
                    "title": f"{code} official catalogue index entry",
                    "content": f"The official BSc Data Science 2026/27 major page lists {code} {title} ({credits} credit units) in the programme curriculum. This index confirms programme inclusion and credit value; prerequisites and teaching details must be read from the linked official course page when available.",
                    "source_url": f"https://www.cityu.edu.hk/catalogue/ug/current/course/{code}.htm",
                    "catalogue_year": "2026/27",
                    "source_status": "published",
                    "course_code": code,
                })
        for item in source_documents:
            existing = session.query(SourceDocumentRow).filter_by(
                source_url=item["source_url"], title=item["title"]
            ).first()
            if existing is None:
                existing = SourceDocumentRow(
                    document_type=item["document_type"],
                    title=item["title"],
                    content=item["content"],
                    official=True,
                    source_url=item["source_url"],
                    catalogue_year=item.get("catalogue_year"),
                    term_id=item.get("term_id"),
                    source_status=item.get("source_status", "published"),
                    verified_at=item.get("verified_at", verified_at),
                    course_code=item.get("course_code"),
                )
                session.add(existing)
        from app.storage.database import ProgrammeCourseScopeRow
        # The current product phase intentionally excludes CS from the DSC
        # candidate scope; remove stale seed scopes from earlier iterations.
        session.query(ProgrammeCourseScopeRow).filter(
            ProgrammeCourseScopeRow.programme == "DSC",
            ProgrammeCourseScopeRow.course_code.like("CS%"),
        ).delete(synchronize_session=False)
        for item in payload.get("programme_course_scopes", []):
            existing = session.query(ProgrammeCourseScopeRow).filter_by(
                programme=item["programme"], catalogue_year=item["catalogue_year"], course_code=item["course_code"]
            ).first()
            if existing is None:
                session.add(ProgrammeCourseScopeRow(
                    programme=item["programme"],
                    catalogue_year=item["catalogue_year"],
                    course_code=item["course_code"],
                    scope=item["scope"],
                    source_url="https://www.cityu.edu.hk/catalogue/ug/current/Major/BSC1_DSC-1.htm",
                ))
        session.commit()
        print(f"loaded {len(payload['courses'])} courses, {len(source_documents)} source documents, and {len(payload.get('programme_course_scopes', []))} programme scopes into {database_url}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
