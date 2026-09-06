"""Run the broader natural-language routing evaluation set."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.evaluation import evaluate_routes


if __name__ == "__main__":
    cases = json.loads((ROOT / "evals" / "semantic_route_cases.json").read_text(encoding="utf-8"))
    print(json.dumps(evaluate_routes(cases), ensure_ascii=False, indent=2))
