# Cobaju

Cobaju is an AI-powered wardrobe assistant. This repository currently contains
the Phase 0 monorepo foundation: the approved React frontend, a minimal FastAPI
backend, and Moonrepo tasks for running both applications.

## Repository layout

```text
.
├── apps/
│   ├── frontend/       # Approved React, TypeScript, and Vite prototype
│   └── backend/        # Minimal FastAPI application
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

The environment file contains only local defaults in Phase 0. Neither
application requires a secret yet.

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

The applications can also be started with their native package managers:

```bash
corepack pnpm@10.12.1 --dir apps/frontend dev
uv run --project apps/backend uvicorn app.main:app --reload
```

## Build and test

```bash
moon run frontend:build
moon run backend:test
moon run :check
```

The project-wide `:check` target runs the frontend production build and backend
test suite. No database or external service is needed in Phase 0.
