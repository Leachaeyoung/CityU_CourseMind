"""Deterministic ranking primitives for the future Planner Agent."""
from typing import Iterable, Mapping


def rank_candidates(candidates: Iterable[Mapping], interests: Iterable[str] = ()) -> list[dict]:
    """Rank already-eligible candidate records without changing hard filters.

    Ranking is deliberately explainable: prerequisite failures are always last;
    then interest/title matches are used as soft signals. Seat availability is
    intentionally excluded because the imported AIMS data is a snapshot, not a
    live registration feed.
    The LLM may explain this order later, but cannot bypass the filters.
    """
    interest_tokens = {token.strip().lower() for token in interests if token.strip()}
    ranked = []
    for candidate in candidates:
        prereq = candidate.get("prerequisite", {})
        eligible = bool(prereq.get("eligible", False))
        title = str(candidate.get("title", "")).lower()
        interest_hits = sum(token in title for token in interest_tokens)
        score = (100 if eligible else 0) + min(interest_hits, 5) * 10
        ranked.append({**candidate, "planner_score": score,
                       "planner_reasons": (["prerequisites satisfied"] if eligible else ["prerequisites incomplete"])
                       + (["matches profile interests"] if interest_hits else [])
                       + ["seat availability excluded: AIMS data is a snapshot"]})
    return sorted(ranked, key=lambda item: (-item["planner_score"], item.get("course_code", "")))
