# Voice Agent QA Platform

A FastAPI + PostgreSQL + Celery service that tests AI voice agents (via Retell AI) by simulating persona-driven phone calls and scoring them against user-defined evaluation criteria with an LLM judge (OpenAI).

## Architecture

```
                   ┌──────────────────────┐
POST /test-runs ─▶ │   FastAPI API        │ ──enqueue──▶ ┌────────────┐
                   │   (CRUD + orchestr.) │               │  Celery    │
                   └───┬─────────┬────────┘               │  worker    │
                       │         │                        └─────┬──────┘
                       ▼         ▼                              │
                   PostgreSQL   Redis                            │
                       ▲         ▲                               │
   Retell webhook ─────┘         └─────── evaluate_call ─────────┘
                                                │
                                          OpenAI (judge)
```

1. `POST /test-runs` creates a run with N queued `calls` and dispatches `place_call` tasks.
2. `place_call` workers build a persona prompt and ask Retell to place an outbound call.
3. Retell fires a webhook at `/api/v1/webhooks/retell` when the call ends → transcript saved → `evaluate_call` enqueued.
4. `evaluate_call` runs each criterion through OpenAI with structured output and writes per-criterion scores.
5. `aggregate_run_if_complete` computes the weighted aggregate score and marks the run.

## Data model

- `personas` — tone/personality/goal/constraints/prompt_instructions
- `test_cases` — persona_id + context
- `evaluation_criteria` — boolean|score, weight, instructions
- `test_runs` — status, requested/completed/failed, total_cost, aggregate_score, pass
- `calls` — retell_call_id, status, transcript, recording_url, cost, error
- `call_evaluations` — per-criterion result (passed|score, reasoning, confidence)

## Quick start (Docker)

```bash
cp .env.example .env
# fill in RETELL_API_KEY, RETELL_AGENT_ID, RETELL_FROM_NUMBER, OPENAI_API_KEY

docker compose up --build
# API:           http://localhost:8000
# OpenAPI docs:  http://localhost:8000/docs
# Health:        http://localhost:8000/health/ready
```

The `api` service runs Alembic migrations on start.

## Local dev (without Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# start postgres + redis however you like, then:
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
```

## Smoke test the full flow

```bash
# 1) Persona
PID=$(curl -s -X POST localhost:8000/api/v1/personas \
  -H 'content-type: application/json' \
  -d '{"name":"Impatient Caller","tone":"frustrated","goal":"Get a refund"}' | jq -r .id)

# 2) Test case + criteria
TCID=$(curl -s -X POST localhost:8000/api/v1/test-cases \
  -H 'content-type: application/json' \
  -d "{\"name\":\"Refund flow\",\"persona_id\":\"$PID\",\"context\":\"Order #123\",\"criteria\":[
        {\"name\":\"Acknowledged issue\",\"type\":\"boolean\",\"instructions\":\"Did agent acknowledge the late delivery?\",\"weight\":0.4},
        {\"name\":\"Politeness\",\"type\":\"score\",\"max_score\":5,\"instructions\":\"Rate politeness 0-5.\",\"weight\":0.6}
      ]}" | jq -r .id)

# 3) Run it (small & capped)
RUN=$(curl -s -X POST localhost:8000/api/v1/test-runs \
  -H 'content-type: application/json' \
  -d "{\"test_case_id\":\"$TCID\",\"agent_phone_number\":\"+15555550123\",\"num_calls\":2,\"max_cost_usd\":0.50,\"max_duration_sec\":120}")
echo "$RUN" | jq

# 4) Poll
curl -s localhost:8000/api/v1/test-runs/$(echo $RUN | jq -r .id) | jq
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST/GET/PATCH/DELETE | `/api/v1/personas[/{id}]` | Persona CRUD |
| POST/GET/PATCH/DELETE | `/api/v1/test-cases[/{id}]` | Test case CRUD (criteria accepted nested) |
| POST | `/api/v1/test-cases/{id}/criteria` | Add a criterion |
| GET/PATCH/DELETE | `/api/v1/criteria/{id}` | Criterion detail/update/delete |
| POST | `/api/v1/test-runs` | Start a run (batch) |
| GET | `/api/v1/test-runs` | List with `test_case_id`, `status`, `date_from`, `date_to` |
| GET | `/api/v1/test-runs/{id}` | Run + criteria breakdown |
| GET | `/api/v1/test-runs/{id}/calls` | Calls in run |
| POST | `/api/v1/test-runs/{id}/retry` | Re-enqueue failed/timeout calls |
| GET | `/api/v1/calls/{id}` | Call + transcript + recording + evaluations |
| POST | `/api/v1/webhooks/retell` | Retell `call_ended` webhook |

## Tests

```bash
pytest -q
# pytest will use testcontainers to spin up a throwaway postgres; requires Docker.
```

## Configuration

See [`.env.example`](.env.example). Key knobs:
- `DEFAULT_PASS_THRESHOLD` — aggregate score ≥ threshold ⇒ run passes (default 0.7)
- `MAX_CALLS_PER_RUN`, `MAX_COST_PER_RUN_USD`, `MAX_CALL_DURATION_SEC` — safety caps
- `EVAL_MODEL` — OpenAI model for the judge (default `gpt-4o-mini`)

## Out of scope (v1)

- No UI (use `/docs`)
- No auth / multi-tenancy
- No "improvement suggestions" meta-summary (structure is there)
- Single eval provider (OpenAI)
