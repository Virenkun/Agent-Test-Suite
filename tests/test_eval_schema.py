from decimal import Decimal

from app.integrations.openai_client import _eval_schema, _prompt
from app.models.criterion import CriterionType, EvaluationCriterion


def test_boolean_schema_requires_passed():
    c = EvaluationCriterion(
        name="ok", type=CriterionType.BOOLEAN, instructions="x", weight=Decimal("1")
    )
    schema = _eval_schema(c)
    assert "passed" in schema["required"]
    assert "score" not in schema["properties"]
    assert schema["additionalProperties"] is False


def test_score_schema_bounds_by_max_score():
    c = EvaluationCriterion(
        name="quality", type=CriterionType.SCORE, instructions="x",
        weight=Decimal("1"), max_score=10,
    )
    schema = _eval_schema(c)
    assert schema["properties"]["score"]["maximum"] == 10.0
    assert "score" in schema["required"]


def test_prompt_mentions_rubric():
    c = EvaluationCriterion(
        name="friendly", type=CriterionType.SCORE, instructions="be friendly",
        weight=Decimal("1"), max_score=5,
    )
    prompt = _prompt(c)
    assert "0–5" in prompt or "0-5" in prompt or "0–5" in prompt
    assert "be friendly" in prompt
