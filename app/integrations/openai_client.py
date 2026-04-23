import json
from dataclasses import dataclass
from decimal import Decimal

from openai import OpenAI

from app.config import get_settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.models.criterion import CriterionType, EvaluationCriterion

log = get_logger(__name__)

# Rough per-1K-token pricing for cost tracking (USD). Safe upper bound;
# keep conservative since exact rates vary and we only need approximations.
_MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
}


@dataclass
class EvaluationResult:
    passed: bool | None
    score: float | None
    reasoning: str
    confidence: float
    cost_usd: Decimal


def _eval_schema(criterion: EvaluationCriterion) -> dict:
    props: dict = {
        "reasoning": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    required = ["reasoning", "confidence"]
    if criterion.type == CriterionType.BOOLEAN:
        props["passed"] = {"type": "boolean"}
        required.insert(0, "passed")
    else:
        props["score"] = {
            "type": "number",
            "minimum": 0,
            "maximum": float(criterion.max_score or 5),
        }
        required.insert(0, "score")
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _prompt(criterion: EvaluationCriterion) -> str:
    if criterion.type == CriterionType.BOOLEAN:
        rubric = f"Return `passed: true` if the criterion is met, else `passed: false`."
    else:
        rubric = (
            f"Score the criterion on a 0–{criterion.max_score} scale. "
            "Higher means better adherence."
        )
    return (
        "You are an objective QA evaluator for AI voice agent conversations.\n"
        f"Criterion: {criterion.name}\n"
        f"Instructions: {criterion.instructions}\n"
        f"{rubric}\n"
        "Always include concise reasoning (1–3 sentences) and a confidence between 0 and 1."
    )


def _estimate_cost(model: str, usage: object) -> Decimal:
    pricing = _MODEL_PRICING.get(model, {"input": 0.001, "output": 0.003})
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cost = (prompt_tokens / 1000) * pricing["input"] + (
        completion_tokens / 1000
    ) * pricing["output"]
    return Decimal(str(round(cost, 6)))


class OpenAIEvaluator:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ExternalServiceError("OPENAI_API_KEY not configured")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.eval_model

    def evaluate(
        self, *, transcript: str, criterion: EvaluationCriterion
    ) -> EvaluationResult:
        schema = _eval_schema(criterion)
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _prompt(criterion)},
                    {"role": "user", "content": f"Conversation transcript:\n\n{transcript}"},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "evaluation",
                        "schema": schema,
                        "strict": True,
                    },
                },
                temperature=0,
            )
        except Exception as e:
            log.error("openai_eval_failed", error=str(e), criterion_id=str(criterion.id))
            raise ExternalServiceError(f"OpenAI API error: {e}") from e

        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        cost = _estimate_cost(self._model, resp.usage)

        return EvaluationResult(
            passed=parsed.get("passed"),
            score=parsed.get("score"),
            reasoning=parsed.get("reasoning", ""),
            confidence=float(parsed.get("confidence", 0.0)),
            cost_usd=cost,
        )
