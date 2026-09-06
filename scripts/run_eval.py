"""Run the checked-in CourseMind routing regression set."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.evaluation import evaluate_routes


if __name__ == "__main__":
    cases = json.loads((ROOT / "evals" / "coursemind_cases.json").read_text(encoding="utf-8"))
    # Keep the human-curated seed set compact while exercising paraphrase-like
    # variants in the offline regression run. These suffixes do not add intent
    # keywords; they test that harmless wording does not change routing.
    suffixes = ["，请说明依据", "，请简要解释", "，给我官方来源", "，我想了解清楚"]
    expanded = list(cases)
    variant_index = 0
    while len(expanded) < 50:
        case = cases[variant_index % len(cases)]
        suffix = suffixes[variant_index % len(suffixes)]
        expanded.append({**case, "id": f"{case['id']}-variant-{variant_index + 1}", "message": case["message"] + suffix})
        variant_index += 1
    cases = expanded[:50]
    print(json.dumps(evaluate_routes(cases), ensure_ascii=False, indent=2))
