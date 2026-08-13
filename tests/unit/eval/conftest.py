"""Fixtures for evaluation tests."""

import pytest

from eval.cases import GoldenCase


@pytest.fixture
def golden_case() -> GoldenCase:
    """A case whose ground truth matches what `pipeline_models` is scripted to return."""
    return GoldenCase.model_validate(
        {
            "id": "overwatering-test",
            "category": "watering",
            "plant": {"name": "Kitchen basil", "species": "Basil"},
            "species_confidence": 0.9,
            "symptoms": {
                "overall_vigor": "declining",
                "soil_condition": "wet",
                "symptoms": [
                    {
                        "description": "yellowing lower leaves",
                        "position": "lower_leaves",
                        "severity": "act_this_week",
                    }
                ],
            },
            "answers": {"light_hours": "four hours indirect"},
            "ground_truth": "overwatering",
            "also_acceptable": ["root-rot"],
        }
    )
