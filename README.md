# Cobaju

Cobaju is an AI-powered wardrobe assistant. The current application includes:

- a React, TypeScript, and Vite frontend with Login, Wardrobe, Stylist, and
  Lookbook screens;
- a FastAPI backend with SQLModel, SQLite, Alembic, JWT authentication, and
  ownership-scoped wardrobe and recommendation APIs;
- validated local clothing-image uploads processed by a Redis-backed Celery
  worker;
- OpenRouter clothing analysis, embeddings, chat guardrails, stylist
  generation, and Style Critic evaluation;
- Chroma semantic wardrobe search and a trusted, user-scoped MCP wardrobe
  server;
- deterministic recommendation validation, one targeted repair at most, and
  optional Langfuse tracing.

The chat endpoint does not save recommendations automatically. It returns a
short-lived signed receipt after validation, and the frontend saves a Lookbook
entry only when the user selects **Save to Lookbook**.

## Repository layout

```text
.
├── apps/
│   ├── frontend/       # Approved React, TypeScript, and Vite prototype
│   └── backend/        # FastAPI, SQLModel, SQLite, and Alembic
├── docs/               # Observability and supporting documentation
├── infrastructure/     # Reserved for deployment files; currently empty
├── .moon/              # Moonrepo workspace configuration
├── AGENTS.md
└── ROADMAP.md
```

## Prerequisites

- [Moonrepo](https://moonrepo.dev/) 2.x
- [Corepack](https://nodejs.org/api/corepack.html) (included with Node.js)
- [uv](https://docs.astral.sh/uv/) 0.11 or newer
- Node.js 20.19 or newer, or Node.js 22.12 or newer
- Python 3.12 or newer
- Redis 7 or newer

## First-time setup

From the repository root:

```bash
cp .env.example .env
corepack pnpm@10.12.1 --dir apps/frontend install --frozen-lockfile
uv sync --project apps/backend
```

The root `.env` is loaded by the backend and Celery worker. Before running the
backend, replace `JWT_SECRET_KEY` with a private random value. One way to
generate it is:

```bash
openssl rand -hex 32
```

Create or update the local SQLite database before starting the backend:

```bash
moon run backend:migrate
```

The frontend has no required `.env` file. Its development server uses port
`8443` by default and proxies `/api` to `http://127.0.0.1:8000`. To use another
frontend development port, set `PORT` in the shell that starts the frontend:

```bash
PORT=9000 moon run frontend:dev
```

## Environment variables

Use [.env.example](.env.example) as the source of truth for documented
operational backend variables. The main groups are:

| Group | Variables | Required when |
|---|---|---|
| Core | `APP_ENVIRONMENT`, `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Local defaults exist; `JWT_SECRET_KEY` must be replaced |
| Storage | `UPLOAD_DIRECTORY`, `CHROMA_DIRECTORY`, `CHROMA_COLLECTION_NAME` | Defaults are suitable for local development |
| Worker | `REDIS_URL`, `CELERY_TASK_MAX_RETRIES`, `CELERY_TASK_RETRY_DELAY_SECONDS` | Image analysis is used |
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_TIMEOUT_SECONDS` | Any AI or embedding workflow is used |
| Clothing analysis | `OPENROUTER_GUARDRAIL_MODEL`, `OPENROUTER_VISION_MODEL` | Uploaded images are analyzed |
| Retrieval | `OPENROUTER_EMBEDDING_MODEL`, `WARDROBE_SEARCH_LIMIT` | Semantic search is used |
| Stylist | `OPENROUTER_CHAT_GUARDRAIL_MODEL`, `OPENROUTER_STYLIST_MODEL`, `OPENROUTER_STYLE_CRITIC_MODEL`, `STYLING_CANDIDATES_PER_CATEGORY`, `STYLIST_MAX_TOOL_CALLS` | Stylist chat is used; the legacy evaluator model can supply the critic fallback |
| Observability | `LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Langfuse export is enabled |

`OPENROUTER_EVALUATOR_MODEL` and `EVALUATOR_PROMPT_VERSION` remain supported
fallbacks for deployments that have not moved to the Style Critic variable
names. Temperature and prompt-version variables in `.env.example` are optional
overrides; the supplied values match the application defaults.

Relative SQLite, upload, and Chroma paths are resolved from `apps/backend`,
regardless of whether a Moonrepo or native command starts the process.

## Run the applications

Run each long-lived process in a separate terminal from the repository root.
Apply migrations before starting the API or worker. A normal local startup
order is Redis, backend, worker, then frontend.

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

The worker is required for uploaded-image analysis. Login, manual wardrobe CRUD,
Lookbook history, and health endpoints can run without it, but queued analyses
will not complete.

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

FastAPI's interactive API documentation is available at
<http://127.0.0.1:8000/docs>.

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
`completed` processing status. Each user may have at most 50 completed items.

Create a pending wardrobe item and upload its original image in one request:

```bash
curl -X POST http://127.0.0.1:8000/wardrobe/items/upload \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -F 'image=@/absolute/path/to/clothing.jpg'
```

This combined endpoint is used by the frontend upload flow. It avoids a
separate placeholder-item request and removes the stored file if database
creation fails. Pending upload drafts do not count toward the 50 confirmed-item
limit.

The earlier endpoint for attaching an image to an existing item remains
available:

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
`failed`. For uploads created through `/wardrobe/items/upload`, preserve the
returned `analysis_token` and include it while polling so a terminal content
rejection can still be reported after its temporary row is removed:

```bash
curl --get http://127.0.0.1:8000/wardrobe/items/ITEM_ID/status \
  --data-urlencode 'analysis_token=ANALYSIS_TOKEN' \
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
Confirmed items created before vector indexing was added are indexed lazily on
their owner's first search.

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

The backend exposes one local MCP server with these tools:

```text
get_styling_candidates
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

Normal Stylist requests make one `get_styling_candidates` call. It returns an
optional anchor, owned IDs, candidates capped per category, and missing required
categories. The lower-level MCP `save_recommendation` tool remains available and
ownership-safe, but the web application does not call it during generation.
Lookbook persistence is a separate authenticated HTTP request initiated by the
user.

Semantic search requires `OPENROUTER_API_KEY` and
`OPENROUTER_EMBEDDING_MODEL`. The other four MCP tools remain usable without an
embedding provider.

## Wardrobe stylist API

Set `OPENROUTER_CHAT_GUARDRAIL_MODEL`, `OPENROUTER_STYLIST_MODEL`, and
`OPENROUTER_STYLE_CRITIC_MODEL` in `.env`. Existing
`OPENROUTER_EVALUATOR_MODEL` values remain a fallback. The guardrail and Style
Critic need strict JSON output; the stylist also needs Chat Completions tool
calling through OpenRouter.

```bash
curl -X POST http://127.0.0.1:8000/chat/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"message":"What can I wear to a smart-casual office?"}'
```

The endpoint rejects explicit prompt injection before an AI call, redirects
unrelated requests, and opens exactly one MCP session. The backend retrieves
wardrobe candidates once through MCP and caches them in the request scope. The
Wardrobe Stylist receives only the user request and reads that cache through its
zero-argument `read_cached_wardrobe_evidence` tool; the tool performs no
retrieval or other I/O. Missing categories are clearly non-owned. Before a
response is returned, deterministic validation rechecks cached owned evidence,
category claims, required-category coverage, and the `Not owned:` label. Valid
drafts reach the tool-free
temperature-`0.0` Style Critic. It returns only `approved`, `issues`, and
`repair_instruction` and checks wardrobe evidence, category coverage, occasion,
refinement instructions, unsupported claims, and exact repetition when previous
outfit evidence is available. A rejection gets one targeted repair using the
already retrieved wardrobe candidates. The repaired result always passes
deterministic validation again and is not sent through an unbounded critic
loop. Malformed critic output may be retried once; a valid rejection is not.
Repair never lists tools, retrieves, or calls `save_recommendation`.

## Recommendation history

The chat response includes an optional `lookbook_save_token` only after the
recommendation passes validation. When the user selects **Save to Lookbook**,
the frontend submits that receipt to `POST /recommendations` with the
conversation's initial styling theme. The backend rechecks item ownership before
saving selected item IDs, the final explanation, an internal approval score,
and the completion timestamp.

List the authenticated user's newest saved records first:

```bash
curl http://127.0.0.1:8000/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

History never returns another user's records. If a selected item is later
deleted, the record remains readable and returns that item with
`available: false`.

Delete only an authenticated user's saved Lookbook entry. This leaves all
wardrobe items and uploaded clothing images unchanged:

```bash
curl -X DELETE http://127.0.0.1:8000/recommendations/RECOMMENDATION_ID \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

## Frontend integration

The approved React interface connects to the backend through `/api`. During
development, Vite provides that proxy.
Register or sign in from the frontend, then use Wardrobe, Add piece, Stylist,
and Lookbook without manually copying a token. The token remains in the browser
local storage key `access_token` and is validated with `/auth/me` when the app
opens. If a protected request reports an expired session, the frontend clears
the token, authenticated state, and protected query cache before returning to
the login screen. Upload creates the pending record and stores the image in one
request, then queues analysis, polls status, and presents generated metadata
for review and confirmation. TanStack Query manages server data, cache
invalidation, loading states, and error states.

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

## AI observability

When enabled, Langfuse traces each stylist request through authentication,
guardrail validation, MCP retrieval, generation, evaluation, deterministic
validation, optional repair, and response formatting. Saving a Lookbook entry
is a separate HTTP request and is not part of the stylist-generation trace.
Structured JSON request logs share the Langfuse trace ID and a safe request ID.
See [`docs/Observability.md`](docs/Observability.md) for the trace hierarchy,
configuration, evaluation metrics, privacy boundaries, and validation steps.

Langfuse remains optional. Set `LANGFUSE_ENABLED=true` with
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` to export
traces. Disabled or incomplete configuration uses a no-op backend and does not
interrupt AI workflows.

## Production deployment

This repository does not currently include Docker, Compose, or
platform-specific deployment manifests. Production infrastructure must provide
the following without changing the application API:

1. Build `apps/frontend/dist` with `moon run frontend:build` and serve it as
   static files.
2. Route same-origin requests under `/api/*` to FastAPI after removing the
   `/api` prefix. The backend routes themselves are `/auth`, `/wardrobe`,
   `/chat`, and `/recommendations`.
3. Run migrations once for each release before starting the new API and worker
   processes.
4. Run FastAPI without `--reload`, for example:

   ```bash
   APP_ENVIRONMENT=production uv run --project apps/backend \
     uvicorn --app-dir apps/backend app.main:app --host 0.0.0.0 --port 8000
   ```

5. Run a separate Celery worker connected to the same Redis and database:

   ```bash
   APP_ENVIRONMENT=production uv run --project apps/backend \
     celery --workdir apps/backend -A app.celery_app:celery_app \
     worker --loglevel=INFO --concurrency=1
   ```

6. Persist and back up the SQLite database, `UPLOAD_DIRECTORY`, and
   `CHROMA_DIRECTORY`. All API, worker, and MCP processes must see the same
   paths.
7. Supply secrets through the deployment platform rather than committing a
   production `.env`. Terminate TLS at the platform or reverse proxy.

The current deployment target uses SQLite, so the documented worker command
uses one Celery process. Keep the API, worker, and persistent data on one host;
do not place SQLite on an unvalidated network filesystem. Validate concurrency
and backup behavior before increasing worker concurrency.

## Troubleshooting

### The frontend loads but API requests fail

For local development, confirm FastAPI is listening on
`http://127.0.0.1:8000` and start the frontend with
`moon run frontend:dev`. A static production build has no Vite proxy; the
production web server must implement the `/api` routing described above.

### Login returns a server error

Confirm that `.env` exists at the repository root and that
`JWT_SECRET_KEY` is not blank or still set to the example value. Restart the
API after changing `.env`.

### Image analysis stays pending

Confirm that Redis responds to `redis-cli ping`, the Celery worker is running,
and the worker uses the same `REDIS_URL`, `DATABASE_URL`, and
`UPLOAD_DIRECTORY` as the API. Check the worker log for OpenRouter
configuration or provider errors.

### Semantic search returns `503`

Set `OPENROUTER_API_KEY` and `OPENROUTER_EMBEDDING_MODEL`, then restart the API.
Also confirm that `CHROMA_DIRECTORY` is writable by the API and MCP processes.

### Stylist chat returns `503`

Verify the OpenRouter API key and the chat guardrail, stylist, and Style Critic
model variables. The configured models must support the structured-output
behavior used by their respective workflows.

### Migrations target the wrong SQLite file

Run migration commands from the repository root exactly as documented. Relative
`DATABASE_URL` values are resolved from `apps/backend`; use an absolute
`sqlite:////...` URL when a deployment needs a database elsewhere.

### SQLite reports `database is locked`

Stop migrations from running concurrently with application startup, use the
documented single-process Celery worker for this SQLite deployment, and confirm
that every process points to the same local database file. Do not delete the
database to clear a lock.

### Port 8443 is already in use

Choose another frontend development port in the command environment:

```bash
PORT=9000 moon run frontend:dev
```

## Build and test

```bash
moon run frontend:build
moon run frontend:test
moon run backend:migrate
moon run backend:test
moon run :check
```

Run only the service and MCP tool tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_mcp.py
```

Run only the chat tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_chat.py
```

Run only the evaluation and repair tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_evaluation.py
```

Run only the recommendation-history tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_recommendation_history.py
```

The project-wide `:check` target runs the frontend production build, frontend
tests, and backend test suite. Tests use mocked vision and deterministic
embedding providers, so they require no running Redis server, OpenRouter
credits, or Langfuse connection.
