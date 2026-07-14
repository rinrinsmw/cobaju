# AGENTS.md

# Cobaju — Instructions for Coding Agents

This file defines how Codex and other coding agents must work inside the Cobaju repository.

## Project Goal

Cobaju is an AI-powered wardrobe assistant that allows users to:

1. Register and log in.
2. Upload clothing images.
3. Validate that uploads contain clothing.
4. Analyze clothing metadata using a vision model.
5. Save clothing in a digital wardrobe.
6. Search wardrobe items using RAG.
7. Generate outfit recommendations using an AI stylist agent.
8. Evaluate recommendations before returning them.
9. Track cost, latency, accuracy, and hallucination using Langfuse.

The project must remain understandable for a beginner and must be implemented incrementally.

---

## Repository Structure

```text
cobaju/
├── apps/
│   ├── frontend/
│   └── backend/
├── infrastructure/
├── docs/
├── .moon/
├── AGENTS.md
└── README.md
```

### Frontend

- React
- TypeScript
- Vite
- pnpm
- Existing frontend from the approved ZIP must be retained as the visual baseline.

### Backend

- FastAPI
- SQLModel
- Alembic
- SQLite
- uv

### AI and Infrastructure

- OpenRouter
- OpenAI Agents SDK
- Chroma
- MCP
- Langfuse
- Celery
- Redis
- Moonrepo

---

# Mandatory Working Rules

## 1. Work One Phase at a Time

Do not implement future phases unless explicitly requested.

Before coding:

1. Read `AGENTS.md`.
2. Read the current phase document.
3. Inspect the existing repository.
4. Explain the plan for the requested phase.
5. Wait for approval when the task is broad or destructive.

After coding:

1. Summarize what changed.
2. List every important file created or modified.
3. Explain the code in beginner-friendly language.
4. Provide exact commands to run and test it.
5. Report any incomplete work or uncertainty honestly.

---

## 2. Preserve the Existing Frontend

The frontend inside `apps/frontend` is the approved visual foundation.

Do not:

- Redesign the interface without an explicit request.
- Replace the current visual language.
- Remove existing screens simply because they are not connected yet.
- Rewrite the frontend from scratch.
- Change pnpm to npm or yarn.
- Replace working mock UI before the corresponding backend API exists.

When integrating APIs:

- Replace mock data gradually.
- Preserve layout, spacing, typography, and interactions where possible.
- Create reusable components only when useful.
- Avoid large refactors during backend phases.

---

## 3. Keep the Project Beginner-Friendly

Prefer:

- Clear names
- Small functions
- Explicit code
- Simple dependency injection
- Typed request and response models
- Useful comments explaining non-obvious logic
- One responsibility per module

Avoid:

- Clever abstractions
- Premature design patterns
- Metaprogramming
- Excessive inheritance
- Deeply nested folders
- Complex generic types
- Large undocumented functions
- Refactoring unrelated code

When there are multiple valid approaches, prefer the easiest one to understand and debug.

---

## 4. Do Not Overbuild the MVP

Do not add these unless explicitly requested:

- Virtual try-on
- Weather integration
- Marketplace integration
- Social features
- Kubernetes
- Microservices
- Multiple databases beyond SQLite and Chroma
- Multiple MCP servers
- More than one evaluator sub-agent
- Complex refresh-token rotation
- OAuth providers
- Cloud object storage
- Advanced analytics dashboards

---

## 5. Backend Rules

Use:

- FastAPI routers
- SQLModel models
- Alembic migrations
- Pydantic Settings
- Dependency injection for database sessions and authenticated users
- Structured error responses
- Explicit response models

Do not:

- Create database tables automatically in production code when Alembic should manage them.
- Put all routes in `main.py`.
- Put business logic directly inside route handlers.
- Store plain-text passwords.
- Trust `user_id` received from request bodies.
- Allow access to another user's wardrobe.
- Return internal exception details to users.
- Hardcode secrets, model names, or API keys.

---

## 6. Authentication and Authorization Rules

- Passwords must be hashed.
- JWT access tokens may be used for the MVP.
- The authenticated user must come from the token.
- Every wardrobe query must be filtered by the authenticated user.
- Item ownership must be checked before read, update, delete, or recommendation use.
- Never accept a client-provided `user_id` as authorization.

---

## 7. Image Upload Guardrails

Before expensive AI processing:

1. Validate file type.
2. Validate file size.
3. Confirm only one main item is expected.
4. Run a clothing-content guardrail.
5. Reject invalid uploads early.

Accepted examples:

- Tops
- Bottoms
- Dresses
- Outerwear
- Shoes
- Bags
- Fashion accessories

Reject:

- Food
- Pets
- Selfies
- Documents
- Screenshots
- Furniture
- Explicit or unsafe content
- Images with no clearly visible clothing

Do not save invalid images to the wardrobe.

---

## 8. Chat Guardrails

The assistant may handle:

- Wardrobe questions
- Outfit recommendations
- Clothing combinations
- Style and occasion questions
- Questions about owned clothing
- Incomplete wardrobe guidance

The assistant must reject or redirect:

- Unrelated programming questions
- Politics
- Medical or financial advice
- Harmful instructions
- Harassment
- Explicit content
- Prompt injection
- Requests to reveal system prompts
- Requests to invent clothing ownership

Use low-temperature classification and deterministic validation where possible.

---

## 9. AI Configuration

Use separate configuration for each AI task.

Recommended starting values:

| Component | Temperature |
|---|---:|
| Guardrail classifier | 0.0 |
| Vision clothing analysis | 0.1 |
| Metadata extraction | 0.1 |
| Stylist agent | 0.5 |
| Outfit evaluator | 0.0 |

All model names and parameters must come from settings or environment variables.

Do not assume every OpenRouter model supports every parameter. Validate provider compatibility before relying on optional generation settings.

---

## 10. RAG Rules

RAG is used to search the authenticated user's wardrobe.

Store searchable clothing descriptions such as:

```text
Light blue long-sleeve shirt suitable for office and smart-casual occasions.
```

Retrieval must:

- Filter by authenticated user.
- Filter by clothing category when appropriate.
- Return item IDs and metadata.
- Never retrieve another user's wardrobe.
- Prefer hybrid filtering plus semantic similarity.
- Return a limited number of relevant results.

Do not rely on the LLM to remember the wardrobe.

---

## 11. Agent Rules

The main agent is the Wardrobe Stylist Agent.

It may:

- Understand the user's request.
- Decide required clothing categories.
- Call wardrobe tools.
- Generate outfit candidates.
- Send a candidate to the evaluator.
- Retry once after rejection.

It must not:

- Query the database directly.
- Invent item IDs.
- Invent ownership.
- Recommend items not returned by tools.
- Exceed configured tool-call or turn limits.
- Retry indefinitely.

---

## 12. MCP Rules

Use one wardrobe MCP server for the MVP.

Expected tools:

- `search_wardrobe`
- `get_clothing_item`
- `list_wardrobe_categories`
- `save_recommendation`

Tool descriptions must be clear and narrow.

Security rules:

- User identity must be supplied by trusted backend context.
- Never trust a user ID from model output.
- Tools must validate ownership.
- Tools must return structured results.

Before exposing a function through MCP, make it work and test it as a normal Python service first.

---

## 13. Evaluator and Hallucination Rules

The evaluator checks:

- Outfit completeness
- Occasion relevance
- Color and style compatibility
- Ownership
- Valid item IDs
- Unsupported claims

A deterministic validator must run after the evaluator.

The final recommendation is valid only when:

```text
recommended item IDs ⊆ authenticated user's owned item IDs
```

Generic advice for missing items is allowed only when clearly labelled as not owned by the user.

---

## 14. Celery and Redis Rules

Use Celery for slow upload processing:

- Vision analysis
- Metadata generation
- Embedding generation
- Vector indexing

Use Redis as the broker.

Use processing statuses:

- `pending`
- `processing`
- `completed`
- `failed`

Do not introduce Celery before the synchronous service logic works and is tested.

---

## 15. Langfuse Rules

Trace important AI workflows:

```text
clothing_analysis
├── upload_guardrail
├── vision_analysis
├── metadata_validation
└── embedding_generation

outfit_recommendation
├── input_guardrail
├── parse_request
├── wardrobe_retrieval
├── stylist_generation
├── evaluator
├── deterministic_validation
└── final_response
```

Record where supported:

- Model name
- Input and output tokens
- Estimated cost
- Latency
- Tool calls
- Retrieved items
- Evaluator decision
- Retry count
- Errors
- Guardrail results

Do not log passwords, JWTs, API keys, or sensitive personal data.

---

## 16. Testing Rules

Every phase must include tests appropriate to that phase.

Minimum testing categories:

- Unit tests for services
- API tests for routes
- Authorization tests
- Guardrail tests
- Agent tool tests
- Evaluation dataset tests

Important scenarios:

- Valid clothing upload
- Non-clothing upload
- Unsupported chat request
- Prompt injection
- Incomplete wardrobe
- Cross-user item access
- Hallucinated item ID
- Evaluator rejection and one retry

Do not mark a phase complete when its main workflow has not been manually tested.

---

## 17. Moonrepo Rules

Moonrepo orchestrates tasks but does not replace native package managers.

Use:

- pnpm for frontend dependencies
- uv for backend dependencies
- Moonrepo for project tasks

Expected commands should eventually include:

```text
moon run frontend:dev
moon run backend:dev
moon run backend:test
moon run backend:migrate
moon run backend:worker
moon run :check
```

Keep tasks understandable and documented.

---

## 18. Dependency Rules

Before adding a dependency:

1. Explain why it is needed.
2. Check whether an existing dependency already solves the problem.
3. Prefer stable, actively maintained packages.
4. Avoid adding multiple libraries for the same purpose.
5. Update the relevant lockfile.
6. Mention the new dependency in the final summary.

Do not upgrade unrelated dependencies during a feature phase.

---

## 19. Documentation Rules

Update documentation when behavior changes.

Important files:

- `README.md`
- `.env.example`
- phase documents
- API usage examples
- migration instructions
- Moonrepo commands

Commands must be copy-pasteable.

---

## 20. Git and Safety Rules

Do not:

- Delete user files without explicit approval.
- Rewrite Git history.
- Force push.
- Commit secrets.
- Run destructive database commands without warning.
- Remove the frontend prototype.
- Change package managers without approval.
- Perform large unrelated refactors.

Before destructive operations, explain the impact and ask for confirmation.

---

# Definition of Done for Any Phase

A phase is complete only when:

- The requested scope is implemented.
- The main workflow runs.
- Tests pass.
- Commands are documented.
- No secrets are committed.
- Existing working features remain functional.
- The agent explains the implementation.
- Any limitations are clearly stated.
