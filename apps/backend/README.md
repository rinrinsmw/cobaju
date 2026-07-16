# Cobaju backend

This FastAPI service contains Cobaju's backend through Phase 5:

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
- pytest coverage for settings, sessions, health, authentication, CRUD,
  authorization, validation, wardrobe limits, storage, and mocked AI calls.

Celery, Redis, Chroma, stylist agents, and MCP remain out of scope.

## Wardrobe endpoints

All routes use the authenticated user from the JWT and never accept a client
`user_id`:

```text
POST   /wardrobe/items
GET    /wardrobe/items
GET    /wardrobe/items/{item_id}
PATCH  /wardrobe/items/{item_id}
DELETE /wardrobe/items/{item_id}
POST   /wardrobe/items/{item_id}/image
POST   /wardrobe/items/{item_id}/analyze
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

Analysis first runs a temperature-0.0 clothing guardrail. Rejected images are
detached and deleted. Accepted images go to the configured vision model at
temperature 0.1 and produce only `name`, `category`, `color`, and optional
`description`. Pydantic validates these fields before saving. The owner can
edit the pending draft through `PATCH`, then call `confirm` to mark it
`completed`. `analysis_completed` prevents confirmation before AI analysis.

For real calls, set `OPENROUTER_API_KEY`, `OPENROUTER_GUARDRAIL_MODEL`, and
`OPENROUTER_VISION_MODEL` in the root `.env`. Both models must support image
input and strict structured outputs. Langfuse tracing is disabled by default;
enable it with `LANGFUSE_ENABLED=true` and the standard Langfuse key and host
variables. Image bytes and secrets are not included in trace inputs.

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

Run the backend tests:

```bash
moon run backend:test
```

Run only the mocked Phase 5 tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_clothing_analysis.py
```

The API requires `JWT_SECRET_KEY` in the repository root `.env` before login
tokens can be issued. Copy `.env.example` and replace its placeholder with a
private random value such as the output of `openssl rand -hex 32`.

Native uv commands are also available:

```bash
uv run --project apps/backend alembic -c apps/backend/alembic.ini upgrade head
uv run --project apps/backend pytest apps/backend/tests
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --reload
```
