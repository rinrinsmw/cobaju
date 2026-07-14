# ROADMAP.md

# Cobaju — Phase-by-Phase Implementation Roadmap

This roadmap is designed so that the project can be built with Codex one phase at a time while remaining understandable for a beginner.

---

# How to Use This Roadmap

For every new phase, give Codex this prompt:

```text
Read AGENTS.md and ROADMAP.md.

We are working only on Phase [NUMBER]: [PHASE NAME].

Before editing:
1. inspect the repository,
2. explain the current state,
3. propose a small implementation plan,
4. list the files likely to change,
5. identify risks and decisions.

Then implement only this phase.

After editing:
1. summarize what changed,
2. list modified files,
3. explain the important code,
4. provide exact commands to run,
5. provide exact commands to test,
6. report test results and limitations,
7. stop.
```

Do not ask Codex to build the entire project in one prompt.

---

# Phase 0 — Repository and Moonrepo Foundation

## Goal

Create the Cobaju monorepo and confirm that the approved frontend and a minimal backend can run independently.

## Scope

- Create the root repository structure.
- Initialize Git.
- Configure Moonrepo.
- Move the approved frontend into `apps/frontend`.
- Retain pnpm and its lockfile.
- Create `apps/backend` using uv.
- Add a minimal FastAPI health endpoint.
- Add basic Moonrepo tasks.
- Create `.env.example`.
- Add setup instructions to `README.md`.

## Do Not Include

- Authentication.
- Database models.
- AI integration.
- Celery.
- Redis.
- RAG.
- MCP.

## Completion Criteria

- Existing frontend still runs.
- FastAPI health endpoint responds.
- Moonrepo can run frontend and backend tasks.
- Setup commands are documented.

---

# Phase 1 — Backend Foundation and Database

## Goal

Create a clean FastAPI foundation using SQLModel, SQLite, Alembic, and application settings.

## Scope

- FastAPI app structure.
- Pydantic Settings.
- SQLite connection.
- SQLModel session dependency.
- Alembic configuration.
- Initial migration.
- Health endpoint.
- Database health check.
- Basic backend test setup.
- Moonrepo backend test and migration tasks.

## Do Not Include

- Authentication.
- Clothing models.
- AI calls.
- Celery.
- Chroma.

## Completion Criteria

- Backend starts.
- Alembic migration runs.
- Database session works.
- Tests pass.

---

# Phase 2 — Authentication

## Goal

Implement secure user registration and login.

## Scope

- User SQLModel table.
- User create and read schemas.
- Password hashing.
- Register endpoint.
- Login endpoint.
- JWT access token.
- Current-user dependency.
- Protected test endpoint.
- Authentication tests.

## Do Not Include

- Google OAuth.
- Email verification.
- Password reset.
- Refresh-token rotation.

## Completion Criteria

- User can register.
- User can log in.
- Protected endpoints reject unauthenticated requests.
- Passwords are not stored in plain text.
- Duplicate email and invalid password are tested.

---

# Phase 3 — Wardrobe Model and CRUD

## Goal

Allow authenticated users to manage clothing metadata without AI.

## Scope

- Clothing item SQLModel table.
- Clothing categories.
- Processing status.
- Create endpoint.
- List endpoint.
- Detail endpoint.
- Update endpoint.
- Delete endpoint.
- Ownership checks.
- Maximum 15 confirmed items.
- Alembic migration.
- API and authorization tests.

## Do Not Include

- Image upload.
- Vision model.
- Embeddings.
- RAG.
- Agent.

## Completion Criteria

- Users can manage their own items.
- Cross-user access is blocked.
- Wardrobe limit is enforced.
- Migration succeeds.
- Tests pass.

---

# Phase 4 — Image Upload and Local Storage

## Goal

Allow users to upload one clothing image safely.

## Scope

- Multipart upload endpoint.
- JPG, PNG, and WebP validation.
- Maximum 5 MB.
- Safe generated filenames.
- Local upload directories.
- Original image path in the database.
- Upload status.
- File cleanup after failure.
- Upload tests.

## Do Not Include

- Vision analysis.
- Clothing classifier.
- Celery.
- Background removal.

## Completion Criteria

- Valid files upload.
- Invalid formats are rejected.
- Oversized files are rejected.
- Files cannot overwrite one another.
- Ownership remains enforced.
- Tests pass.

---

# Phase 5 — Clothing Guardrail and Vision Analysis

## Goal

Reject non-clothing images and generate editable clothing metadata.

## Scope

- OpenRouter client configuration.
- Vision model configuration.
- Clothing-content classifier.
- Structured metadata output.
- Temperature 0.0 for guardrail.
- Temperature 0.1 for vision analysis.
- Metadata validation.
- User review and confirmation workflow.
- Langfuse clothing-analysis trace.
- Mockable AI service.
- AI service tests using mocked responses.

## Do Not Include

- Celery.
- Chroma.
- Stylist agent.
- MCP.

## Completion Criteria

- Clothing images are accepted.
- Clear non-clothing images are rejected.
- Metadata follows a stable schema.
- Unsupported claims are avoided.
- Users can edit metadata.
- Tests do not require real paid API calls.

---

# Phase 6 — Celery and Redis Processing

## Goal

Move the working clothing-analysis workflow into a background task.

## Scope

- Redis configuration.
- Celery application.
- Clothing processing task.
- Status transitions.
- Error handling.
- Limited retry behavior.
- Status polling endpoint.
- Moonrepo worker task.
- Frontend processing state connection where needed.

## Important Rule

Reuse the synchronous service created in Phase 5.

Do not duplicate vision or metadata logic inside Celery tasks.

## Completion Criteria

- Upload creates a pending or processing item.
- Celery runs the analysis.
- Status becomes completed or failed.
- Worker starts through Moonrepo.
- Failed processing does not leave inconsistent records.

---

# Phase 7 — Embeddings and Chroma RAG

## Goal

Create a searchable wardrobe knowledge layer.

## Scope

- Embedding model settings.
- Clothing description builder.
- Chroma collection.
- Add vector records.
- Update vector records.
- Delete vector records.
- Semantic wardrobe search.
- Filter by authenticated user.
- Category-aware retrieval.
- Retrieval tests.
- Langfuse retrieval spans.

## Do Not Include

- Agent framework.
- MCP.
- Evaluator.

## Completion Criteria

- Confirmed clothing items are indexed.
- Updated metadata updates the vector record.
- Deleted items are removed from Chroma.
- Search returns only the current user's items.
- Relevant items rank above unrelated items.
- Tests pass.

---

# Phase 8 — Wardrobe Services and MCP

## Goal

Expose tested wardrobe functionality as structured MCP tools.

## Scope

- Normal Python wardrobe services.
- MCP server.
- `search_wardrobe`.
- `get_clothing_item`.
- `list_wardrobe_categories`.
- `save_recommendation`.
- Structured inputs and outputs.
- Trusted user context.
- Ownership validation.
- Tool tests.

## Completion Criteria

- Normal services work independently.
- MCP wrappers remain thin.
- Tools cannot access another user's data.
- Tool descriptions are clear.
- Tool outputs are structured.
- Tests pass.

---

# Phase 9 — Stylist Agent and Chat Guardrails

## Goal

Create the main Wardrobe Stylist Agent.

## Scope

- OpenAI Agents SDK.
- OpenRouter-compatible model settings.
- Stylist temperature 0.5.
- Chat scope classifier.
- Prompt-injection resistance.
- Wardrobe tool use through MCP.
- Required-category planning.
- Outfit candidate generation.
- Incomplete wardrobe handling.
- Maximum turns.
- Maximum tool calls.
- One response schema.
- Langfuse recommendation trace.

## Do Not Include

- Multiple main agents.
- Unlimited retries.
- Generic internet fashion search.
- Weather integration.

## Completion Criteria

- Valid fashion requests are handled.
- Unrelated requests are redirected.
- Prompt injection is rejected.
- Agent uses wardrobe tools.
- Agent does not claim ownership without valid item IDs.
- Incomplete wardrobes do not produce invented items.

---

# Phase 10 — Evaluator and Deterministic Validation

## Goal

Validate every recommendation before returning it.

## Scope

- Outfit evaluator sub-agent.
- Evaluator temperature 0.0.
- Occasion checks.
- Completeness checks.
- Color compatibility.
- Style compatibility.
- Deterministic item ID validation.
- Ownership validation.
- Unsupported-claim validation.
- One retry maximum.
- Hallucination logging.
- Evaluation tests.

## Completion Criteria

- Invalid item IDs are blocked.
- Cross-user items are blocked.
- Evaluator can reject a candidate.
- Stylist retries no more than once.
- Generic missing-item suggestions are clearly labelled.
- Tests pass.

---

# Phase 11 — Recommendation History

## Goal

Save and retrieve completed outfit recommendations.

## Scope

- Recommendation SQLModel table.
- Original user request.
- Selected item IDs.
- Explanation.
- Evaluation score.
- Timestamp.
- History API.
- Ownership rules.
- Existing frontend history screen integration.

## Completion Criteria

- Users see only their own history.
- Saved recommendations reference valid clothing IDs.
- Historical records handle deleted clothing safely.
- Tests pass.

---

# Phase 12 — Full Frontend Integration

## Goal

Connect the approved React frontend to the real backend without redesigning it.

## Scope

- Preserve the approved UI.
- Add or finalize routing.
- Add TanStack Query.
- Authentication state.
- Login and registration integration.
- Wardrobe API integration.
- Upload integration.
- Processing status.
- Metadata confirmation.
- Stylist recommendation integration.
- Recommendation history integration.
- Loading states.
- Empty states.
- Error states.

## Do Not Include

- Major redesign.
- New product features.
- Package-manager changes.
- Replacing pnpm.

## Completion Criteria

- Mock data is removed only where APIs exist.
- Main user journey works end to end.
- Approved visual design remains recognizable.
- Mobile layout remains usable.
- Frontend build passes.

---

# Phase 13 — Langfuse Evaluation and Metrics

## Goal

Measure quality, reliability, performance, and cost.

## Scope

- Evaluation dataset of approximately 15–20 scenarios.
- Cost per clothing analysis.
- Cost per recommendation.
- Latency per workflow stage.
- Outfit validity score.
- Hallucination rate.
- Tool success rate.
- Guardrail accuracy.
- Invalid-image rejection accuracy.
- False rejection rate.
- Presentable evaluation summary.

## Suggested Metrics

| Metric | Purpose |
|---|---|
| Recommendation validity | Outfit quality |
| Hallucination rate | Unsupported items or claims |
| Average latency | User experience |
| Cost per request | Efficiency |
| Tool success rate | Agent reliability |
| Guardrail accuracy | Safety and scope control |

## Completion Criteria

- Metrics come from real runs.
- Failed scenarios are documented.
- Results are not invented.
- Langfuse traces show the full workflow.

---

# Phase 14 — Deployment and Final Demo

## Goal

Prepare a stable final-project demonstration.

## Scope

- Docker Compose.
- Frontend container.
- FastAPI container.
- Redis.
- Celery worker.
- Persistent SQLite volume.
- Persistent uploads volume.
- Persistent Chroma storage.
- Environment configuration.
- Nginx if needed.
- Seed or demo data.
- Final README.
- Backup local demo plan.

## Completion Criteria

- Application starts using documented commands.
- Main demo flow is repeatable.
- Secrets are excluded.
- Data persists across restarts.
- Local backup demo is available.

---

# Recommended Commit Strategy

Use one or more commits per phase.

Examples:

```text
chore: initialize moonrepo monorepo
feat: add backend database foundation
feat: implement JWT authentication
feat: add wardrobe CRUD
feat: add clothing image uploads
feat: add clothing image guardrails
feat: process clothing with celery
feat: add wardrobe vector retrieval
feat: expose wardrobe MCP tools
feat: add stylist agent
feat: validate outfit recommendations
feat: add recommendation history
feat: integrate frontend APIs
test: add agent evaluation dataset
chore: add deployment configuration
```

---

# When to Stop and Ask for Help

Stop the current phase when:

- A command fails repeatedly.
- A dependency conflicts with the environment.
- A migration may destroy data.
- A change would redesign the approved frontend.
- OpenRouter model behavior differs from expectations.
- MCP or Agents SDK compatibility is unclear.
- The task requires a future phase.
- A destructive operation is required.
- You do not understand an important implementation decision.
