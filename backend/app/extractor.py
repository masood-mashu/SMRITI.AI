"""Development extraction boundary used until the Gemini adapter is added."""

from datetime import date
from typing import Any


def extract_report(*, filename: str, use_fixture: bool = False) -> dict[str, Any]:
    """Return structured extraction output without inventing facts for real files.

    The fixture is synthetic and opt-in so it is safe for local demo development.
    A future Gemini adapter can implement this same return contract.
    """
    if not use_fixture:
        return {
            "facts": [],
            "explanation": f"Extraction stub received {filename}; no facts extracted.",
        }

    return {
        "facts": [
            {
                "fact_type": "condition",
                "fact_key": "Type 2 diabetes",
                "fact_value": "Recorded in synthetic demo profile",
                "effective_date": date(2026, 1, 15),
                "is_emergency_relevant": True,
                "confidence": 0.99,
            },
            {
                "fact_type": "medication",
                "fact_key": "Metformin",
                "fact_value": "500 mg",
                "unit": "mg",
                "effective_date": date(2026, 1, 15),
                "is_emergency_relevant": True,
                "confidence": 0.99,
            },
            {
                "fact_type": "allergy",
                "fact_key": "Penicillin",
                "fact_value": "Severe reaction",
                "effective_date": date(2026, 1, 15),
                "is_emergency_relevant": True,
                "confidence": 0.99,
            },
        ],
        "explanation": "Synthetic development fixture: a sample longitudinal health profile was extracted.",
    }
