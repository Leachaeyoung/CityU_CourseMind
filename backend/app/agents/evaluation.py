"""Small regression checks for routing and Planner behaviour."""
from typing import Iterable, Mapping

from .router import route_request


def evaluate_routes(cases: Iterable[Mapping]) -> dict:
    total = passed = 0
    failures = []
    for case in cases:
        total += 1
        actual = route_request(str(case["message"])).intent.value
        if actual == case["expected_intent"]:
            passed += 1
        else:
            failures.append({"id": case.get("id"), "expected": case["expected_intent"], "actual": actual})
    return {"total": total, "passed": passed, "accuracy": passed / total if total else 0.0, "failures": failures}
