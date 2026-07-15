# Cobaju

Cobaju is an AI-powered wardrobe assistant. This repository currently contains
the approved React frontend and a FastAPI backend through Phase 2: environment
settings, SQLModel, SQLite, Alembic migrations, and JWT authentication.

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

The environment file contains local Phase 2 defaults. Before running the
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
test suite. Phase 2 uses a local SQLite file and needs no external database.
