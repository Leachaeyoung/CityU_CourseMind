"""Run 20 deterministic end-to-end planning regression cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents.planner import rank_candidates


def main():
    cases = []
    for i in range(20):
        eligible = i % 2 == 0
        cases.append({
            "course_code": f"DSC{4000 + i}", "title": "Language Models" if i == 0 else "Data Science elective",
            "prerequisite": {"eligible": eligible},
            "sections": [{"credit_units": 3, "slots": [{"weekday": 1, "start_minute": 540, "end_minute": 650}]}],
        })
    ranked = rank_candidates(cases, interests=["language"])
    assert len(ranked) == 20
    assert all(item["prerequisite"]["eligible"] for item in ranked[:10])
    assert ranked[0]["course_code"] == "DSC4000"
    assert all("available_seats" not in item for item in ranked)
    print("passed 20/20 end-to-end planning cases")


if __name__ == "__main__":
    main()
