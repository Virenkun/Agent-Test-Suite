import pytest


@pytest.mark.asyncio
async def test_create_list_update_delete_persona(client):
    resp = await client.post(
        "/api/v1/personas",
        json={
            "name": "Impatient Caller",
            "tone": "frustrated",
            "personality": "Interrupts often, demands quick answers.",
            "goal": "Get a refund",
            "constraints": {"max_patience_sec": 30},
            "prompt_instructions": "Always interrupt after 5 seconds of agent monologue.",
        },
    )
    assert resp.status_code == 201, resp.text
    persona = resp.json()
    pid = persona["id"]
    assert persona["name"] == "Impatient Caller"

    resp = await client.get("/api/v1/personas")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1

    resp = await client.patch(f"/api/v1/personas/{pid}", json={"tone": "calm"})
    assert resp.status_code == 200
    assert resp.json()["tone"] == "calm"

    resp = await client.delete(f"/api/v1/personas/{pid}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/personas/{pid}")
    assert resp.status_code == 404
