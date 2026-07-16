# Cobaju backend

This FastAPI service contains Cobaju's backend through Phase 11:

- settings loaded from environment variables or the repository root `.env`;
- a SQLModel engine and per-request session dependency;
- a local SQLite database;
- Alembic migration configuration and an initial revision;
- API and database health checks;
- a user table managed by Alembic;
- Argon2 password hashing and short-lived JWT access tokens;
- registration, login, and protected current-user routes;
- a clothing item table with category and processing-status enums;
- authenticated wardrobe create, list, detail, partial update, and delete routes;
- ownership checks that hide other users' items;
- a maximum of 15 completed items per user;
- authenticated multipart uploads attached to owned wardrobe items;
- JPG, PNG, and WebP content validation with a 5 MB limit;
- UUID-based filenames in configurable user-specific local directories;
- database path/status updates and cleanup after failed uploads or deletion;
- OpenRouter settings with separate guardrail and vision models;
- a synchronous, mockable clothing guardrail and metadata analysis service;
- strict metadata validation and an explicit review/confirmation workflow;
- optional nested Langfuse clothing-analysis observations;
- Redis-backed Celery dispatch with limited retry behavior;
- an ownership-safe clothing-processing status endpoint;
- a Moonrepo worker task;
- OpenRouter text-embedding configuration and a mockable embedding provider;
- persistent Chroma records for confirmed clothing metadata;
- vector updates and deletions tied to wardrobe lifecycle changes;
- lazy backfill of confirmed items created before Phase 7;
- semantic search with mandatory user and optional category filters;
- optional Langfuse wardrobe-retrieval spans;
- normal ownership-safe Python services for stylist-facing wardrobe operations;
- a standalone FastMCP server with four structured wardrobe tools;
- trusted host-supplied MCP user context that is absent from model inputs;
- confirmed ownership validation for recommendation candidates;
- pytest coverage for settings, sessions, health, authentication, CRUD,
  authorization, validation, wardrobe limits, storage, mocked AI calls, queue
  failures, status polling, task retries, semantic ranking, vector lifecycle,
  retrieval authorization, category filters, MCP schemas, tool delegation, and
  cross-user recommendation rejection;
- one authenticated OpenAI Agents SDK Wardrobe Stylist Agent;
- deterministic prompt-injection rejection and a temperature-0.0 chat classifier;
- required-category planning and bounded MCP wardrobe tool use;
- owned item IDs grounded through `save_recommendation`;
- clearly separated incomplete-wardrobe guidance;
- one structured chat response and optional Langfuse recommendation traces;
- mocked chat, grounding, limit, incomplete-wardrobe, and API tests.
- a separate temperature-0.0 outfit evaluator for occasion, completeness,
  color, style, and unsupported-claim checks;
- database-backed final ID, ownership, category, and missing-item label checks;
- hallucination outcomes in optional Langfuse validation observations;
- exactly one retry after evaluator or deterministic rejection;
- mocked evaluation, cross-user, invalid-ID, unsupported-claim, and retry tests.
- a recommendation table populated only after final evaluation succeeds;
- an authenticated, newest-first `GET /recommendations` history endpoint;
- safe unavailable-item output when historically selected clothing is deleted;
- persistence, ownership-isolation, deleted-item, and history API tests.

## Recommendation history

The chat service writes history only after both evaluation layers accept the
final candidate. The MCP `save_recommendation` tool remains a pre-evaluation
ownership validator and therefore still returns `persisted: false`.

```bash
curl http://127.0.0.1:8000/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Records contain the original request, selected IDs, explanation, score, and
timestamp. Current item details are resolved at read time. Deleted items stay
in the selected ID list and are returned with `available: false`.

## Stylist chat endpoint

The authenticated `POST /chat/recommendations` workflow now includes Phase 11.
Configure
`OPENROUTER_CHAT_GUARDRAIL_MODEL` for strict JSON output and
`OPENROUTER_STYLIST_MODEL` for strict JSON plus Chat Completions tool calling.
Configure `OPENROUTER_EVALUATOR_MODEL` for strict structured output. The
classifier and evaluator run at temperature `0.0`; the stylist runs at `0.5`.

Explicit prompt injection is rejected before a paid call. Allowed requests run
one stylist against the trusted current user's MCP process. Owned selections are
returned only when `save_recommendation` validated the same IDs. Unavailable
categories are returned separately as generic, non-owned guidance.
Each candidate is compared with confirmed database evidence by the evaluator,
then deterministic code rechecks item IDs, ownership, categories, and explicit
`Not owned:` labels. A rejection is sent back to the stylist once. If the retry
also fails, the endpoint returns its existing generic HTTP 503 response.

```bash
curl -X POST http://127.0.0.1:8000/chat/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Build a smart-casual office outfit from my wardrobe"}'
```

`STYLIST_MAX_TURNS` and `STYLIST_MAX_TOOL_CALLS` bound the run. The SDK's
default OpenAI trace exporter is disabled. When `LANGFUSE_ENABLED=true`, Cobaju
creates an `outfit_recommendation` trace without the message body or secrets.

## Wardrobe MCP server

Phase 8 exposes the tested service layer through exactly four tools:

```text
search_wardrobe
get_clothing_item
list_wardrobe_categories
save_recommendation
```

The wrappers do not accept `user_id`. An opt-in FastAPI dependency takes the
verified `current_user.id` and launches one stdio child process for that user.
Existing authenticated endpoints do not depend on it and therefore do not
launch MCP processes.

The child identity is private runtime state, not application configuration. It
must never come from an HTTP request, tool argument, or shared `.env`. The MCP
server rejects a missing, malformed, non-positive, or nonexistent SQLite user
before exposing tools. Closing the dependency always closes the client session,
stdio streams, and child process, including when the caller raises an exception.

`search_wardrobe` needs the OpenRouter embedding settings described below. The
server can still list categories, get confirmed items, and validate a
recommendation when semantic retrieval is not configured.

`save_recommendation` rejects missing, unconfirmed, cross-user, duplicate, or
invalid IDs. It returns the validated owned item records and `persisted: false`;
the final chat workflow performs durable saving after evaluation succeeds.

## Wardrobe endpoints

All routes use the authenticated user from the JWT and never accept a client
`user_id`:

```text
POST   /wardrobe/items
GET    /wardrobe/items
GET    /wardrobe/items/search?q=QUERY&category=OPTIONAL&limit=OPTIONAL
GET    /wardrobe/items/{item_id}
PATCH  /wardrobe/items/{item_id}
DELETE /wardrobe/items/{item_id}
POST   /wardrobe/items/{item_id}/image
POST   /wardrobe/items/{item_id}/analyze
GET    /wardrobe/items/{item_id}/status
POST   /wardrobe/items/{item_id}/confirm
```

Create and update bodies use `name`, `category`, `color`, and optional
`description`. Categories are `top`, `bottom`, `dress`, `outerwear`, `shoes`,
`bag`, and `accessory`. A manual create is immediately `completed`; processing
status is returned by the API but cannot be set by the client.

The multipart image endpoint uses the field name `image`. It accepts one JPG,
PNG, or WebP file up to 5 MB, verifies its binary signature, stores it under
the configured `UPLOAD_DIRECTORY`, and changes the item status to `pending`.
Client filenames are never used for storage. A second upload to the same item
is rejected with HTTP 409.

The analysis endpoint claims an item as `processing`, sends its database ID to
Redis, and returns HTTP 202. The Celery worker first runs a temperature-0.0
clothing guardrail. Rejected images are detached and deleted. Accepted images
go to the configured vision model at temperature 0.1 and produce only `name`,
`category`, `color`, and optional `description`. Pydantic validates these
fields before saving. Poll `GET /wardrobe/items/{item_id}/status`; successful
analysis reports `completed` with `needs_confirmation: true`. The owner can
edit the underlying pending draft through `PATCH`, then call `confirm` to mark
the wardrobe item `completed`. The processing state blocks duplicate work while
the task runs, and `analysis_completed` blocks re-analysis after metadata is
ready.

Provider failures retry according to `CELERY_TASK_MAX_RETRIES` and
`CELERY_TASK_RETRY_DELAY_SECONDS`, then remain `failed`. If Redis cannot accept
the task, the API returns HTTP 503 and restores the item to retryable `pending`.

For real calls, set `OPENROUTER_API_KEY`, `OPENROUTER_GUARDRAIL_MODEL`, and
`OPENROUTER_VISION_MODEL` in the root `.env`. Both models must support image
input and strict structured outputs. Langfuse tracing is disabled by default;
enable it with `LANGFUSE_ENABLED=true` and the standard Langfuse key and host
variables. Image bytes and secrets are not included in trace inputs.

Set `OPENROUTER_EMBEDDING_MODEL` to a text embedding model available through
OpenRouter. Confirmed records are stored in `CHROMA_DIRECTORY` under
`CHROMA_COLLECTION_NAME`. Search embeds the query, filters Chroma by the
authenticated user's ID, optionally filters by category, and returns no more
than 15 structured results. `WARDROBE_SEARCH_LIMIT` supplies the default.

```bash
curl --get http://127.0.0.1:8000/wardrobe/items/search \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  --data-urlencode 'q=smart blue office shirt' \
  --data-urlencode 'category=top'
```

## Run from the repository root

Install dependencies and apply migrations:

```bash
uv sync --project apps/backend
moon run backend:migrate
```

Start the API:

```bash
moon run backend:dev
```

Start Redis, then start the worker in another terminal:

```bash
redis-server
moon run backend:worker
```

Run the backend tests:

```bash
moon run backend:test
```

Run only the mocked clothing-analysis and Phase 6 processing tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_clothing_analysis.py
```

Run only the Phase 7 retrieval tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_retrieval.py
```

Run only the Phase 8 service and MCP tool tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_mcp.py
```

Run only the Phase 9 chat and stylist tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_chat.py
```

Run only the Phase 10 evaluator and deterministic validation tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_evaluation.py
```

Run only the Phase 11 recommendation history tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_recommendation_history.py
```

The API requires `JWT_SECRET_KEY` in the repository root `.env` before login
tokens can be issued. Copy `.env.example` and replace its placeholder with a
private random value such as the output of `openssl rand -hex 32`.

Native uv commands are also available:

```bash
uv run --project apps/backend alembic -c apps/backend/alembic.ini upgrade head
uv run --project apps/backend pytest apps/backend/tests
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --reload
uv run --project apps/backend celery --workdir apps/backend -A app.celery_app:celery_app worker --loglevel=INFO
```
