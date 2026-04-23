from app.integrations.retell_client import build_dynamic_variables
from app.models.persona import Persona
from app.models.test_case import TestCase


def test_build_dynamic_variables_includes_persona_and_context():
    p = Persona(
        name="Grumpy",
        tone="annoyed",
        personality="short tempered",
        goal="get a refund",
        constraints={"escalate_after_sec": 30},
        prompt_instructions="Interrupt if on hold > 5s.",
    )
    tc = TestCase(name="x", persona_id=p.id, context="Order #123 was late by 4 days.")
    vars_ = build_dynamic_variables(p, tc)
    assert vars_["persona_name"] == "Grumpy"
    assert vars_["persona_tone"] == "annoyed"
    assert "escalate_after_sec" in vars_["persona_constraints"]
    assert "Order #123" in vars_["test_case_context"]
    assert "Interrupt" in vars_["persona_instructions"]


def test_build_dynamic_variables_empty_constraints():
    p = Persona(name="Plain", constraints={})
    tc = TestCase(name="x", persona_id=p.id)
    vars_ = build_dynamic_variables(p, tc)
    assert vars_["persona_constraints"] == "None"
    assert vars_["test_case_context"] == ""
