import pytest


@pytest.mark.asyncio
async def test_create_test_case_with_criteria_and_trigger_run(client):
    # Create persona
    resp = await client.post(
        "/api/v1/personas",
        json={"name": "Polite Customer", "goal": "book an appointment"},
    )
    persona_id = resp.json()["id"]

    # Create test case with 2 criteria
    resp = await client.post(
        "/api/v1/test-cases",
        json={
            "name": "Booking flow QA",
            "description": "Validate booking flow end-to-end",
            "persona_id": persona_id,
            "context": "User wants to book for Friday 3pm",
            "criteria": [
                {
                    "name": "Confirmed booking",
                    "type": "boolean",
                    "instructions": "Did the agent confirm a specific date and time?",
                    "weight": 0.4,
                },
                {
                    "name": "Politeness",
                    "type": "score",
                    "instructions": "Rate politeness on 1-5.",
                    "weight": 0.6,
                    "max_score": 5,
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    tc = resp.json()
    assert len(tc["criteria"]) == 2

    # Add another criterion
    resp = await client.post(
        f"/api/v1/test-cases/{tc['id']}/criteria",
        json={
            "name": "No dead air",
            "type": "boolean",
            "instructions": "Agent should not have gaps longer than 5s.",
            "weight": 0.2,
        },
    )
    assert resp.status_code == 201, resp.text

    # Get test case and verify 3 criteria
    resp = await client.get(f"/api/v1/test-cases/{tc['id']}")
    assert len(resp.json()["criteria"]) == 3


@pytest.mark.asyncio
async def test_score_criterion_requires_max_score(client):
    resp = await client.post("/api/v1/personas", json={"name": "x"})
    persona_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/test-cases",
        json={
            "name": "bad",
            "persona_id": persona_id,
            "criteria": [{"name": "c", "type": "score", "instructions": "x", "weight": 1}],
        },
    )
    assert resp.status_code == 422
