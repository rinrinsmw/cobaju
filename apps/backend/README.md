# Cobaju backend

This FastAPI service contains Cobaju's current backend:

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
- a maximum of 50 completed items per user;
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
- lazy backfill of confirmed items created before vector indexing was added;
- semantic search with mandatory user and optional category filters;
- optional Langfuse wardrobe-retrieval spans;
- normal ownership-safe Python services for stylist-facing wardrobe operations;
- a standalone FastMCP server with a high-level styling-candidate tool;
- trusted host-supplied MCP user context that is absent from model inputs;
- confirmed ownership validation for recommendation candidates;
- pytest coverage for settings, sessions, health, authentication, CRUD,
  authorization, validation, wardrobe limits, storage, mocked AI calls, queue
  failures, status polling, task retries, semantic ranking, vector lifecycle,
  retrieval authorization, category filters, MCP schemas, tool delegation, and
  cross-user recommendation rejection;
- one authenticated OpenAI Agents SDK Wardrobe Stylist Agent;
- deterministic prompt-injection rejection and a temperature-0.0 chat classifier;
- one capped `get_styling_candidates` retrieval per Stylist request;
- one zero-argument, read-only Stylist tool for request-cached wardrobe evidence;
- owned item IDs grounded through cached MCP evidence;
- clearly separated incomplete-wardrobe guidance;
- one structured chat response and optional Langfuse recommendation traces;
- mocked chat, grounding, limit, incomplete-wardrobe, and API tests.
- a separate, tool-free temperature-0.0 Style Critic with an exact structured
  approval, issues, and repair-instruction contract;
- database-backed final ID, ownership, category, and missing-item label checks;
- hallucination outcomes in optional Langfuse validation observations;
- exactly one tool-free repair after deterministic or Style Critic rejection;
- mocked evaluation, cross-user, invalid-ID, unsupported-claim, and repair tests.
- a recommendation table populated only after the user explicitly saves a
  final evaluated result;
- an authenticated, newest-first `GET /recommendations` history endpoint;
- safe unavailable-item output when historically selected clothing is deleted;
- persistence, ownership-isolation, deleted-item, and history API tests.

## Recommendation history

The chat service does not write recommendation history. After deterministic
validation accepts the final candidate, it returns a short-lived, signed
`lookbook_save_token`. The frontend sends that receipt to `POST /recommendations`
only when the user clicks **Save to Lookbook**. The save endpoint binds the
receipt to the authenticated user and rechecks item ownership before writing.
The separate Lookbook save request includes the conversation's initial styling
theme as its display title. Stylist chat requests remain unchanged and later
refinement prompts are still used to generate the latest outfit.

```bash
curl http://127.0.0.1:8000/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

```bash
curl -X POST http://127.0.0.1:8000/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"save_token":"TOKEN_FROM_CHAT_RESPONSE"}'
```

Records contain the original request, selected IDs, explanation, score, and
timestamp. Current item details are resolved at read time. Deleted items stay
in the selected ID list and are returned with `available: false`.

## Stylist chat endpoint

The authenticated `POST /chat/recommendations` workflow uses the complete
guardrail, retrieval, generation, evaluation, and repair pipeline. Configure
`OPENROUTER_CHAT_GUARDRAIL_MODEL` for strict JSON output and
`OPENROUTER_STYLIST_MODEL` for strict JSON plus Chat Completions tool calling.
Configure `OPENROUTER_STYLE_CRITIC_MODEL` for strict structured output.
`OPENROUTER_EVALUATOR_MODEL` remains a deployment-compatible fallback. The
classifier and Style Critic run at temperature `0.0`; the stylist runs at
`0.5`.

Explicit prompt injection is rejected before a paid call. Allowed requests run
one request-scoped session against the trusted current user's MCP process. One
`get_styling_candidates` call returns the optional anchor, all owned IDs, capped
candidate groups, and missing required categories. Unavailable categories are
returned separately as generic, non-owned guidance. That result is cached in the
request-scoped Stylist. The initial Agent receives only the user request and
reads the cache through `read_cached_wardrobe_evidence`, a zero-argument tool
that performs no MCP, database, Chroma, or network call. Deterministic code first
rechecks item IDs against that cached evidence, categories,
required-category coverage, and explicit `Not owned:` labels. Candidates that
fail are sent once to a tool-free repair model together with the original
structured response, violations, and wardrobe candidates retained from MCP
tool results. The repair does not reopen MCP, list tools, retrieve again, or
save. Before critique, user-visible messages and reasons are rebuilt from the
selected cached item names, colors, and categories so warmer prose cannot add
unsupported wardrobe facts. If a model omits the required-category plan, it is
reconstructed from the response's selected owned and explicitly missing
categories before strict validation. A valid draft then reaches the Style
Critic, which has no tools and returns only `approved`, `issues`, and
`repair_instruction`. A rejection supplies that concise feedback to the one
allowed repair. Malformed structured critic output is retried once, while a
valid rejection is never automatically re-judged. Deterministic validation
always runs after repair. If the final candidate still has an objective
failure, the endpoint returns its existing generic HTTP 503 response.
Recommendation generation never persists a Lookbook entry.

```bash
curl -X POST http://127.0.0.1:8000/chat/recommendations \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Build a smart-casual office outfit from my wardrobe"}'
```

`STYLIST_MAX_TOOL_CALLS` bounds request-scoped MCP calls and
`STYLING_CANDIDATES_PER_CATEGORY` caps each returned group.
`STYLIST_REPAIR_TEMPERATURE` controls the single repair call. The SDK's
default OpenAI trace exporter is disabled. When `LANGFUSE_ENABLED=true`, Cobaju
creates a `stylist_request` trace without the message body or secrets.

## Wardrobe MCP server

The server exposes these structured tools:

```text
get_styling_candidates
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
server can still retrieve styling candidates, list categories, get confirmed
items, and validate a recommendation when semantic retrieval is not configured.

Normal Stylist requests use only `get_styling_candidates` at the MCP boundary.
The model can call only its request-cached evidence reader; it cannot list or
call MCP or the lower-level search/category tools. The MCP `save_recommendation`
tool remains ownership-safe, but the web app's explicit Lookbook action uses the
authenticated recommendations API.

## Wardrobe endpoints

All routes use the authenticated user from the JWT and never accept a client
`user_id`:

```text
POST   /wardrobe/items
POST   /wardrobe/items/upload
GET    /wardrobe/items
GET    /wardrobe/items/search?q=QUERY&category=OPTIONAL&limit=OPTIONAL
GET    /wardrobe/items/{item_id}
PATCH  /wardrobe/items/{item_id}
DELETE /wardrobe/items/{item_id}
POST   /wardrobe/items/{item_id}/image
GET    /wardrobe/items/{item_id}/image
POST   /wardrobe/items/{item_id}/analyze
GET    /wardrobe/items/{item_id}/status
POST   /wardrobe/items/{item_id}/confirm
```

Create and update bodies use `name`, `category`, `color`, and optional
`description`. Categories are `top`, `bottom`, `dress`, `outerwear`, `shoes`,
`bag`, and `accessory`. A manual create is immediately `completed`; processing
status is returned by the API but cannot be set by the client.

For the normal upload flow, `POST /wardrobe/items/upload` combines internal
record creation and image storage in one multipart request using the field name
`image`. The response includes a short-lived `analysis_token` used only by the
status poll. The internal draft is excluded from `GET /wardrobe/items` until
vision analysis succeeds and replaces its temporary metadata. If storage or
database creation fails, neither an orphan file nor an orphan record is kept.

The older `POST /wardrobe/items/{item_id}/image` endpoint remains available for
attaching an image to an existing owned item. Both endpoints accept one JPG,
PNG, or WebP file up to 5 MB, verify its binary signature, and store it under
the configured `UPLOAD_DIRECTORY`. Client filenames are never used for
storage. An existing item accepts only one image.

The analysis endpoint claims an item as `processing`, sends its database ID to
Redis, and returns HTTP 202. The Celery worker first runs a temperature-0.0
clothing guardrail. When a normal new upload is rejected, the worker deletes
the image and its internal database row. A pre-existing successful wardrobe
item is preserved if a newly attached image is rejected. Accepted images go to
the configured vision model at temperature 0.1 and produce only `name`,
`category`, `color`, and optional `description`. Pydantic validates these
fields before saving. Poll
`GET /wardrobe/items/{item_id}/status?analysis_token=TOKEN`; successful analysis
reports `completed` with `needs_confirmation: true`. After terminal content
rejection, the owner-bound token lets this endpoint return HTTP 422 with code
`NO_CLEAR_CLOTHING_ITEM` even though no failed wardrobe row is retained. The
owner can edit a successful pending draft through `PATCH`, then call `confirm`
to mark the wardrobe item `completed`. The processing state blocks duplicate
work while the task runs, and `analysis_completed` blocks re-analysis after
metadata is ready.

Provider failures retry according to `CELERY_TASK_MAX_RETRIES` and
`CELERY_TASK_RETRY_DELAY_SECONDS`, then remain `failed`. If Redis cannot accept
the task, the API returns HTTP 503 and restores the item to retryable `pending`.

For real calls, set `OPENROUTER_API_KEY`, `OPENROUTER_GUARDRAIL_MODEL`, and
`OPENROUTER_VISION_MODEL` in the root `.env`. Both models must support image
input and strict structured outputs. Langfuse tracing is disabled by default;
enable it with `LANGFUSE_ENABLED=true` and the standard Langfuse key and host
variables. Image bytes and secrets are not included in trace inputs.

Tracing uses the shared provider-neutral observability facade. The full stylist
hierarchy, structured logging fields, prompt versions, quality metrics, and
Langfuse validation workflow are documented in
[`../../docs/Observability.md`](../../docs/Observability.md).

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

The root [README](../../README.md) is the primary onboarding guide and contains
the complete environment-variable, frontend, deployment, and troubleshooting
instructions. The commands below are the backend-specific quick reference.

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

Run only the mocked clothing-analysis and worker-processing tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_clothing_analysis.py
```

Run only the retrieval tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_retrieval.py
```

Run only the service and MCP tool tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_mcp.py
```

Run only the chat and stylist tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_chat.py
```

Run only the evaluator and deterministic-validation tests:

```bash
uv run --project apps/backend pytest apps/backend/tests/test_evaluation.py
```

Run only the recommendation-history tests:

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
