"""Run 30 official-evidence retrieval cases against the local database."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents.contracts import EvidenceRequirement
from app.agents.evidence import retrieve_official_evidence
from app.storage.database import build_session_factory


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "evals" / "evidence_cases.json").read_text(encoding="utf-8"))
    database_url = os.getenv("COURSEMIND_DATABASE_URL", f"sqlite:///{root / 'backend' / 'coursemind.db'}")
    session = build_session_factory(database_url)()
    passed = 0
    try:
        for case in cases:
            code = case["course_code"]
            evidence = retrieve_official_evidence(session, code + " course facts", EvidenceRequirement.OFFICIAL_COURSE, catalogue_year="2026/27")
            if any(code == item.source_url.rstrip("/").split("/")[-1].replace(".htm", "").upper() or code in item.title for item in evidence):
                passed += 1
        print(f"passed {passed}/{len(cases)} evidence cases")
        raise SystemExit(0 if passed == len(cases) else 1)
    finally:
        session.close()
