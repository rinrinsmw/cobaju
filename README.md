# Cobaju

Cobaju is an AI-powered wardrobe assistant. This repository currently contains
the approved React frontend and a FastAPI backend through Phase 10: environment
settings, SQLModel, SQLite, Alembic migrations, JWT authentication, and
ownership-safe wardrobe CRUD, validated local image uploads, and synchronous
AI clothing guardrails and vision metadata analysis executed by a Celery worker
through Redis. Confirmed clothing is embedded through OpenRouter, persisted in
Chroma, and available through ownership-filtered semantic search.
The same tested wardrobe operations are exposed as four structured MCP tools
using a trusted server-side user context.
One authenticated Wardrobe Stylist Agent now guards chat scope, plans outfit
categories, calls those MCP tools, and separates validated owned IDs from generic
missing-category advice.
Every candidate now passes through a separate temperature-zero evaluator and a
database-backed deterministic validator. A rejected candidate receives at most
one stylist retry; a second failure is never returned to the user.

## Repository layout

```text
.
├── apps/
│   ├── frontend/       # Approved React, TypeScript, and Vite prototype
│   └── backend/        # FastAPI, SQLModel, SQLite, and Alembic
├── docs/               # Project documentation added in later phases
├── infrastructure/     # Deployment files added in later phases
├── .moon/              # Moonrepo workspace configuration
├── AGENTS.md
└── ROADMAP.md
```

## Prerequisites

- [Moonrepo](https://moonrepo.dev/) 2.x
- [Corepack](https://nodejs.org/api/corepack.html) (included with Node.js)
- [uv](https://docs.astral.sh/uv/) 0.11 or newer
- Python 3.12 or newer
- Redis 7 or newer

## First-time setup

From the repository root:

```bash
cp .env.example .env
corepack pnpm@10.12.1 --dir apps/frontend install --frozen-lockfile
uv sync --project apps/backend
```

The environment file contains local Phase 10 defaults. Before running the
backend, replace `JWT_SECRET_KEY` in `.env` with a private random value. One
way to generate it is:

```bash
openssl rand -hex 32
```

Create or update the local SQLite database before starting the backend:

```bash
moon run backend:migrate
```

## Run the applications

Run each long-lived process in a separate terminal from the repository root.

Redis (native command):

```bash
redis-server
```

Confirm that the broker is reachable:

```bash
redis-cli ping
```

The expected response is `PONG`. To use another Redis instance, change
`REDIS_URL` in `.env`.

Frontend:

```bash
moon run frontend:dev
```

Open <http://localhost:8443>.

Backend:

```bash
moon run backend:dev
```

Celery worker:

```bash
moon run backend:worker
```

The wardrobe MCP stdio server is launched internally only by an endpoint or
service that explicitly requests the authenticated MCP session dependency. The
dependency takes `current_user.id` from the verified JWT, injects it into one
child process, and closes that process with the client session. Existing
authenticated routes do not launch MCP.

Check the API at <http://127.0.0.1:8000/health>. A successful response is:

```json
{"status":"ok"}
```

The database-specific health check is available at
<http://127.0.0.1:8000/health/database> and returns:

```json
{"status":"ok","database":"ok"}
```

## Authentication API

Register an account:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"choose-at-least-8-characters"}'
```

Log in to receive a 30-minute Bearer token:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"choose-at-least-8-characters"}'
```

Use the returned `access_token` to call a protected endpoint:

```bash
curl http://127.0.0.1:8000/auth/me \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

## Wardrobe API

All wardrobe routes require the Bearer token returned by login. Create a
manually confirmed clothing item:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Blue Oxford Shirt","category":"top","color":"light blue","description":"Smart-casual cotton shirt"}'
```

List the authenticated user's items:

```bash
curl http://127.0.0.1:8000/wardrobe/items \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Supported categories are `top`, `bottom`, `dress`, `outerwear`, `shoes`,
`bag`, and `accessory`. Manually created items have a server-controlled
`completed` processing status. Each user may have at most 15 completed items.

Upload one original image to an item you own:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/ITEM_ID/image \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -F 'image=@/absolute/path/to/clothing.jpg'
```

Uploads accept JPG, PNG, and WebP files up to 5 MB. The backend verifies the
file content, generates a unique filename, stores it below
`apps/backend/uploads/<user-id>/`, records the relative original image path,
and changes the item status to `pending`. An item accepts only one original
image.

Queue the uploaded image for background analysis:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/ITEM_ID/analyze \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Configure `OPENROUTER_API_KEY`, `OPENROUTER_GUARDRAIL_MODEL`,
`OPENROUTER_VISION_MODEL`, and `OPENROUTER_EMBEDDING_MODEL` in `.env` first.
The two vision models must support image input
and strict structured outputs. The guardrail uses temperature `0.0`; accepted
images receive validated draft `name`, `category`, `color`, and `description`
metadata from the vision model at temperature `0.1`.

The queueing endpoint returns HTTP `202` with the item in `processing` state.
Poll the authenticated status endpoint until it reports `completed` or
`failed`:

```bash
curl http://127.0.0.1:8000/wardrobe/items/ITEM_ID/status \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

For a successful analysis awaiting review, the response is shaped like:

```json
{
  "item_id": 1,
  "status": "completed",
  "analysis_completed": true,
  "needs_confirmation": true
}
```

The analyzed item remains `pending` with `analysis_completed: true`. Review it
and optionally edit it with `PATCH /wardrobe/items/ITEM_ID`, then confirm it:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/ITEM_ID/confirm \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Confirmation changes the status to `completed`. Rejected non-clothing images
are detached and deleted. Transient AI failures keep the valid image for a
maximum of two retries and then set the item to `failed`. A Redis dispatch
failure restores the item to `pending`, so the request can safely be retried.
Set `LANGFUSE_ENABLED=true` and provide Langfuse credentials to trace the
workflow; telemetry is off by default.

## Semantic wardrobe search

Every manually created confirmed item is indexed immediately. An analyzed item
is indexed only after the owner confirms its metadata. Editing confirmed
metadata replaces its vector record, deleting the item removes the record, and
attaching a new image removes the record until the updated analysis is
confirmed again.
Confirmed items created before Phase 7 are indexed lazily on their owner's
first search.

```bash
curl --get http://127.0.0.1:8000/wardrobe/items/search \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  --data-urlencode 'q=blue shirt for the office' \
  --data-urlencode 'category=top' \
  --data-urlencode 'limit=5'
```

`category` and `limit` are optional. Chroma always filters on the trusted user
ID from the JWT before ranking results. Chroma persists below
`apps/backend/chroma/` by default. Retrieval spans are sent to Langfuse only
when telemetry is enabled.

## Wardrobe MCP tools

Phase 8 adds one local MCP server with these tools:

```text
search_wardrobe
get_clothing_item
list_wardrobe_categories
save_recommendation
```

All tools return structured Pydantic outputs. They reuse normal Python services
that can be tested without MCP. Searches return only confirmed items and recheck
vector matches against current database ownership. Item detail and category
listing apply the same confirmed-item boundary.

MCP identity is a private per-process value created by the backend. It is not a
Pydantic setting and must never be accepted from an HTTP request, MCP tool
argument, or shared `.env`. Startup fails if the identity is missing, malformed,
or does not identify an existing SQLite user. One stdio process and client
session belong to exactly one authenticated user.

`save_recommendation` validates that every selected ID is unique, confirmed,
and owned by the trusted user. Its Phase 8 response has `persisted: false`:
database-backed recommendation history belongs to Phase 11 and is intentionally
not introduced early.

Semantic search requires `OPENROUTER_API_KEY` and
`OPENROUTER_EMBEDDING_MODEL`. The other three MCP tools remain usable without
an embedding provider.

## Wardrobe stylist API

Set `OPENROUTER_CHAT_GUARDRAIL_MODEL`, `OPENROUTER_STYLIST_MODEL`, and
`OPENROUTER_EVALUATOR_MODEL` in `.env`. The guardrail and evaluator need strict
JSON output; the stylist also needs Chat Completions tool calling through
OpenRouter.

```bash
curl -X POST http://127.0.0.1:8000/chat/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"message":"What can I wear to a smart-casual office?"}'
```

The endpoint rejects explicit prompt injection before an AI call, redirects
unrelated requests, caps turns and tool calls, and exposes owned items only when
the MCP server accepted the same IDs. Missing categories are clearly non-owned.
Before a response is returned, the evaluator checks occasion, completeness,
color, style, and unsupported claims at temperature `0.0`. The deterministic
validator then rechecks confirmed ownership directly from SQLite, category
claims, and the `Not owned:` label. Rejected candidates are retried once only.

The applications can also be started with their native package managers:

```bash
corepack pnpm@10.12.1 --dir apps/frontend dev
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --reload
uv run --project apps/backend celery --workdir apps/backend -A app.celery_app:celery_app worker --loglevel=INFO
```

The native Alembic equivalent of the Moon migration command is:

```bash
uv run --project apps/backend alembic -c apps/backend/alembic.ini upgrade head
```

## Build and test

```bash
moon run frontend:build
moon run backend:migrate
moon run backend:test
moon run :check
```

Run only the Phase 8 service and MCP tool tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_mcp.py
```

Run only the Phase 9 chat tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_chat.py
```

Run only the Phase 10 evaluation and retry tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_evaluation.py
```

The project-wide `:check` target runs the frontend production build and backend
test suite. Tests use mocked vision and deterministic embedding providers, so
they require no running Redis server, OpenRouter credits, or Langfuse
connection. Phase 10 does not introduce the recommendation-history table. Full
frontend API and authentication integration remains Phase 12; the approved
prototype's existing processing view is unchanged in this phase.
