"""Run the deterministic synthetic extraction contract evaluation."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from backend.app.extractor import FixtureExtractor


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "synthetic_extraction_cases.json"


def run_evaluation() -> tuple[int, int, int]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    extractor = FixtureExtractor()
    passed = 0
    total_expected = 0
    total_predicted = 0
    adversarial_cases = 0
    for case in cases:
        if case.get("adversarial"):
            adversarial_cases += 1
        result = extractor.extract(
            filename="synthetic.txt",
            content_type="text/plain",
            content=case["report"].encode("utf-8"),
        )
        expected = set(case["expected_fact_keys"])
        predicted = {str(fact["fact_key"]) for fact in result.facts}
        total_expected += len(expected)
        total_predicted += len(predicted)
        missing = expected - predicted
        unexpected = predicted - expected
        if not missing and not unexpected:
            passed += 1
        else:
            print(f"FAIL {case['name']}: missing={sorted(missing)}, unexpected={sorted(unexpected)}")
    if adversarial_cases == 0:
        print("FAIL evaluation suite: no adversarial cases are registered")
        return 0, len(cases), total_expected + total_predicted
    print(f"Adversarial cases covered: {adversarial_cases}")
    return passed, len(cases), total_expected + total_predicted


def main() -> int:
    passed, total, _ = run_evaluation()
    print(f"Synthetic extraction evaluation: {passed}/{total} cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
