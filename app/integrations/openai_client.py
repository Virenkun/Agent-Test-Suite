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

    # ----------- AI drafting helpers -----------

    def generate_persona(self, brief: str) -> dict:
        """Return a dict matching PersonaCreate shape.

        OpenAI strict JSON schema disallows union types and open-ended
        ``additionalProperties: {type: ...}``. We model constraints as an array
        of ``{key, value}`` pairs and coerce it to a dict before returning.
        """
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "tone": {"type": "string"},
                "personality": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
                "prompt_instructions": {"type": "string"},
            },
            "required": [
                "name",
                "tone",
                "personality",
                "goal",
                "constraints",
                "prompt_instructions",
            ],
            "additionalProperties": False,
        }
        system = (
            "You design realistic caller personas for testing AI voice agents. "
            "Given a brief, return a persona JSON. Keep names short and human. "
            "Constraints is an ARRAY of {key, value} string pairs — small "
            "factual knobs the caller carries (e.g. key='patience_sec' "
            "value='60', key='injury_type' value='neck pain'). Prompt "
            "instructions tell the simulator how to behave during the call."
        )
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": brief},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "persona",
                        "schema": schema,
                        "strict": True,
                    },
                },
                temperature=0.8,
            )
        except Exception as e:
            log.error("openai_generate_persona_failed", error=str(e))
            raise ExternalServiceError(f"OpenAI API error: {e}") from e
        parsed = json.loads(resp.choices[0].message.content or "{}")
        # Convert constraints array → dict for PersonaCreate compatibility.
        if isinstance(parsed.get("constraints"), list):
            parsed["constraints"] = {
                str(item.get("key")): item.get("value")
                for item in parsed["constraints"]
                if isinstance(item, dict) and item.get("key")
            }
        return parsed

    def generate_test_case(
        self,
        *,
        brief: str,
        persona_hint: str | None = None,
        desired_criteria_count: int = 5,
    ) -> dict:
        """Return a dict matching TestCaseCreate shape (without persona_id)."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "context": {"type": "string"},
                "criteria": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "type": {"enum": ["boolean", "score"]},
                            "instructions": {"type": "string", "minLength": 1},
                            "weight": {"type": "number", "minimum": 0},
                            "max_score": {"type": ["integer", "null"], "minimum": 1},
                        },
                        "required": [
                            "name",
                            "type",
                            "instructions",
                            "weight",
                            "max_score",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["name", "description", "context", "criteria"],
            "additionalProperties": False,
        }
        system = (
            "You design QA test cases for AI voice agents. Given a brief, "
            "return a test case JSON with a concise name, description, context "
            "for the agent under test, and roughly "
            f"{desired_criteria_count} evaluation criteria. Mix boolean and score "
            "criteria. For score criteria set max_score to 5. For boolean "
            "criteria set max_score to null. Weights should be small positive "
            "numbers summing to roughly 1."
        )
        user_msg = brief
        if persona_hint:
            user_msg = f"Persona: {persona_hint}\n\nBrief: {brief}"
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "test_case",
                        "schema": schema,
                        "strict": True,
                    },
                },
                temperature=0.7,
            )
        except Exception as e:
            log.error("openai_generate_test_case_failed", error=str(e))
            raise ExternalServiceError(f"OpenAI API error: {e}") from e
        return json.loads(resp.choices[0].message.content or "{}")

    def summarize_failures(self, *, payload: dict) -> dict:
        """Given a compact summary of failed evaluations, produce insights."""
        schema = {
            "type": "object",
            "properties": {
                "top_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "criterion": {"type": "string"},
                            "fail_rate": {"type": "number", "minimum": 0, "maximum": 1},
                            "summary": {"type": "string"},
                        },
                        "required": ["criterion", "fail_rate", "summary"],
                        "additionalProperties": False,
                    },
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["top_issues", "suggestions"],
            "additionalProperties": False,
        }
        system = (
            "You review voice-agent QA results and produce concise, actionable "
            "improvement suggestions. Focus on the agent under test, not the "
            "simulated caller. Be specific and prescriptive. 3-5 suggestions."
        )
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "insights",
                        "schema": schema,
                        "strict": True,
                    },
                },
                temperature=0.5,
            )
        except Exception as e:
            log.error("openai_summarize_failures_failed", error=str(e))
            raise ExternalServiceError(f"OpenAI API error: {e}") from e
        return json.loads(resp.choices[0].message.content or "{}")
