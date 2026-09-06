"""Import a reviewed, read-only snapshot exported from AIMS Master Class Schedule."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.storage.database import CourseOfferingRow, SourceDocumentRow, build_session_factory


def main() -> None:
    payload = json.loads((ROOT / "data" / "aims_offerings_2026_A.json").read_text(encoding="utf-8"))
    database_url = os.getenv("COURSEMIND_DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'coursemind.db'}")
    session = build_session_factory(database_url)()
    try:
        for item in payload["offerings"]:
            row = session.query(CourseOfferingRow).filter_by(
                course_code=item["course_code"], term_id=payload["term_id"], section=item["section"]
            ).first()
            if row is None:
                row = CourseOfferingRow(course_code=item["course_code"], term_id=payload["term_id"], section=item["section"], slots=[])
                session.add(row)
            for key in ("crn", "slots", "credit_units", "component_type", "campus", "web_enabled", "level", "available_seats", "capacity", "waitlist_available", "date_start", "date_end", "building", "room", "instructor", "medium", "allowed_majors", "allowed_programmes", "access_note"):
                if key in item:
                    setattr(row, key, item[key])
            row.source_status = payload.get("source_status", "published")
            row.source_url = payload["source_url"]
            row.verified_at = payload["verified_at"]
            row.is_snapshot = True
        source_url = payload["source_url"]
        course_codes = ", ".join(sorted({item["course_code"] for item in payload["offerings"]}))
        existing = session.query(SourceDocumentRow).filter_by(
            source_url=source_url, title="AIMS Master Class Schedule Semester A 2026/27 snapshot"
        ).first()
        if existing is None:
            session.add(SourceDocumentRow(
                document_type="schedule",
                title="AIMS Master Class Schedule Semester A 2026/27 snapshot",
                content=f"Official AIMS Master Class Schedule snapshot for Semester A 2026/27. Imported courses: {course_codes}. It contains section, CRN, meeting time, instructor, and major/programme restrictions for the imported DSC offerings. This is a historical planning snapshot and does not confirm current registration availability.",
                official=True, source_url=source_url, term_id=payload["term_id"],
                source_status=payload.get("source_status", "published"), verified_at=payload["verified_at"],
            ))
        else:
            existing.content = f"Official AIMS Master Class Schedule snapshot for Semester A 2026/27. Imported courses: {course_codes}. It contains section, CRN, meeting time, instructor, and major/programme restrictions for the imported DSC offerings. This is a historical planning snapshot and does not confirm current registration availability."
            existing.verified_at = payload["verified_at"]
        session.commit()
        print(f"loaded {len(payload['offerings'])} AIMS offerings for {payload['term_id']} into {database_url}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
