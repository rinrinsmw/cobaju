# Cobaju

Cobaju is an AI-powered wardrobe assistant. This repository currently contains
the approved React frontend and a FastAPI backend through Phase 5: environment
settings, SQLModel, SQLite, Alembic migrations, JWT authentication, and
ownership-safe wardrobe CRUD, validated local image uploads, and synchronous
AI clothing guardrails and vision metadata analysis.

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

## First-time setup

From the repository root:

```bash
cp .env.example .env
corepack pnpm@10.12.1 --dir apps/frontend install --frozen-lockfile
uv sync --project apps/backend
```

The environment file contains local Phase 5 defaults. Before running the
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

Run each application in a separate terminal from the repository root.

Frontend:

```bash
moon run frontend:dev
```

Open <http://localhost:8443>.

Backend:

```bash
moon run backend:dev
```

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

Analyze the uploaded image synchronously:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/ITEM_ID/analyze \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Configure `OPENROUTER_API_KEY`, `OPENROUTER_GUARDRAIL_MODEL`, and
`OPENROUTER_VISION_MODEL` in `.env` first. Both models must support image input
and strict structured outputs. The guardrail uses temperature `0.0`; accepted
images receive validated draft `name`, `category`, `color`, and `description`
metadata from the vision model at temperature `0.1`.

The analyzed item remains `pending` with `analysis_completed: true`. Review it
and optionally edit it with `PATCH /wardrobe/items/ITEM_ID`, then confirm it:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/ITEM_ID/confirm \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Confirmation changes the status to `completed`. Rejected non-clothing images
are detached and deleted. Transient AI failures keep the valid image for a
retry and set the item to `failed`. Set `LANGFUSE_ENABLED=true` and provide
Langfuse credentials to trace the workflow; telemetry is off by default.

The applications can also be started with their native package managers:

```bash
corepack pnpm@10.12.1 --dir apps/frontend dev
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --reload
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

The project-wide `:check` target runs the frontend production build and backend
test suite. Tests mock the vision provider and require no OpenRouter credits or
Langfuse connection. Phase 5 does not introduce Redis, Celery, Chroma, agents,
or MCP.
