from app.agents.planner import rank_candidates


def test_planner_ranking_is_explainable_and_keeps_prerequisite_failures_last():
    ranked = rank_candidates([
        {"course_code": "DSC4008", "title": "Deep Learning", "prerequisite": {"eligible": False}, "sections": [{"available_seats": 20}]},
        {"course_code": "DSC4070", "title": "Large Language Models", "prerequisite": {"eligible": True}, "sections": [{"available_seats": 5}]},
    ], interests=["language"])
    assert ranked[0]["course_code"] == "DSC4070"
    assert "matches profile interests" in ranked[0]["planner_reasons"]
    assert ranked[1]["planner_score"] < ranked[0]["planner_score"]
