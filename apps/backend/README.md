# Cobaju backend

This FastAPI service contains Cobaju's backend through Phase 7:

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
- pytest coverage for settings, sessions, health, authentication, CRUD,
  authorization, validation, wardrobe limits, storage, mocked AI calls, queue
  failures, status polling, task retries, semantic ranking, vector lifecycle,
  retrieval authorization, and category filters.

Stylist agents and MCP remain out of scope.

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
