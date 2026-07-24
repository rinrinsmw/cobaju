# Cobaju AI Observability

The current observability layer makes a stylist request traceable from HTTP
authentication through quality evaluation. Application code depends on the
provider-neutral `Observability` and `Observation` interfaces. Only
`apps/backend/app/observability.py` imports the Langfuse SDK, so another backend
can be introduced later without rewriting the AI services.

## Trace hierarchy

A successful request appears as one `stylist_request` trace:

```text
stylist_request
├── auth.validate
├── guardrail.validate
├── mcp.get_styling_candidates                     invocation_number=1
├── stylist_generation
│   └── agent.read_cached_wardrobe_evidence         optional if model calls tool
├── deterministic_validation
├── style_critic                                   valid initial drafts only
├── targeted_repair                                optional, cached evidence
├── final_validation                               after optional repair
└── response_formatting
```

If deterministic validation or the Style Critic rejects the first candidate,
`targeted_repair` runs once
with the cached MCP bundle and safe counts. The MCP session stays open, but no
tool listing, retrieval, or persistence call occurs during repair. Generation
never persists a Lookbook entry; saving is a separate authenticated HTTP action
triggered by the user. Final trace output records `mcp_session_count`,
`tool_call_count`, `cached_evidence_tool_call_count`, `candidate_count`,
`cache_reused_during_repair`, and `retrieval_duration_ms`.

The existing `clothing_analysis` and semantic `wardrobe_retrieval` workflows use
the same abstraction. Their compatibility wrapper classes remain small to avoid
unrelated service refactoring.

## Metadata and privacy

Common Stylist-request metadata includes:

- request ID;
- a short SHA-256 user reference, never an email or JWT;
- application version;
- OpenRouter as the provider;
- configured model name;
- prompt version;
- attempt or tool invocation number where applicable.

Request text, JWTs, API keys, image bytes, email addresses, system prompts, and
stack-local secrets are not added to Stylist observations. Inputs use safe
properties such as message length and candidate item count. The older
`clothing_analysis` and `wardrobe_retrieval` observations include internal
numeric item or user IDs in their bounded inputs. Langfuse's trace context
records exceptions and the failed stage; application exceptions continue
propagating to the existing API error handling.

## Span naming and instrumentation points

| Observation | Measures |
|---|---|
| `auth.validate` | JWT validation and user database lookup |
| `guardrail.validate` | Scope classifier latency, model, prompt version and tokens |
| `stylist_generation` | Stylist generation using a registered request-cache reader |
| `agent.read_cached_wardrobe_evidence` | Read-only cached evidence tool duration, success and candidate count |
| `targeted_repair` | One tool-free correction using the same cached evidence |
| `mcp.get_styling_candidates` | Single capped wardrobe retrieval duration and success |
| `style_critic` | Tool-free critic latency, approval status, issue count, model attempts and prompt version |
| `deterministic_validation` | Initial deterministic status and stable failure codes |
| `final_validation` | Post-repair deterministic status and stable failure codes |
| `recommendation_deleted` | Recommendation ID, anonymized user ID, success, and delete latency |
| `response_formatting` | Final status, repair count, tool counts and quality output |

Langfuse derives observation and total trace latency from start/end timestamps.
Agents SDK token totals are sent as input, output, and total usage. Cobaju does
not maintain a pricing table: `cost_details.total` is recorded only when the
provider response includes a numeric cost. A metric absent from a provider or
hidden by an upstream SDK remains absent rather than being guessed.

## Recommendation evaluation

The deterministic validator remains the authoritative machine-checkable gate.
A valid initial draft then reaches the temperature-zero, tool-free Style Critic.
Its output contract is deliberately narrow:

```json
{
  "approved": true,
  "issues": [],
  "repair_instruction": ""
}
```

Approved output must have empty feedback. Rejected output must contain concise
issues and one actionable repair instruction, but never a replacement outfit.
A valid rejection triggers one repair and is not automatically re-evaluated.
Malformed structured output may make one additional model attempt. Every repair
is followed by `final_validation`, and no path bypasses deterministic checks.
Observations store status, stable failure reason, latency, and safe counts—not
the user request, critic prose, JWTs, model credentials, or wardrobe images.

## Structured logs

Every HTTP request emits a compact JSON `request_completed` record containing:

```json
{
  "event": "request_completed",
  "request_id": "client-or-generated-id",
  "trace_id": "langfuse-trace-id-or-null",
  "user_id": "hashed-user-reference-or-null",
  "endpoint": "/chat/recommendations",
  "status": 200,
  "duration_ms": 842.31
}
```

Clients may send `X-Request-ID`; malformed values are replaced. The selected ID
is returned in the response header. Failed requests are logged and re-raised.

A successful Stylist request emits `stylist_request_completed` with status,
total latency, tool and model attempt counts, deterministic failures, and the
Style Critic approval summary. The workflow also emits candidate diagnostic
records containing the schema-bounded response, including selected item IDs and
generated wardrobe-derived prose. Treat application logs as user data and
restrict their access and retention accordingly. A Stylist failure also emits
exactly one sanitized `stylist_request_failed`
record with `request_id`, `trace_id`, `error_type`, `failing_stage`,
`duration_ms`, `tool_call_count`, `model_attempt_count`, stable
`validation_failures` plus backward-compatible `evaluator_failures` and
`evaluator_scores` fields carrying only critic status/counts. The router's
additional human-readable traceback is emitted only when
`APP_ENVIRONMENT=development`; lower-level SDK error loggers may still include
exception tracebacks. Structured logs remain available in every environment.

## Configuration and disabling

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

`LANGFUSE_BASE_URL` remains a backward-compatible alias for `LANGFUSE_HOST`.
Set `LANGFUSE_ENABLED=false` to disable trace export. Missing credentials or an
SDK initialization failure also selects the no-op backend and logs a warning;
the application continues normally.

Prompt versions are independently configurable:

```dotenv
CHAT_GUARDRAIL_PROMPT_VERSION=chat-guardrail-v1
STYLIST_PROMPT_VERSION=stylist-v5
STYLIST_REPAIR_PROMPT_VERSION=stylist-repair-v2
STYLE_CRITIC_PROMPT_VERSION=style-critic-v1
```

## Inspecting and validating traces

1. Configure OpenRouter and Langfuse, migrate the database, and start the API.
2. Sign in and send one `POST /chat/recommendations` request.
3. Copy the response `X-Request-ID` into Langfuse trace search.
4. Open `stylist_request` and compare its children with the hierarchy above.
5. Inspect model observations for usage, model, prompt version, and attempt.
6. Inspect each `mcp.*` observation and the final tool count map.
7. Trigger a controlled provider failure and verify the failed observation and
   parent trace remain visible.
8. Restart with `LANGFUSE_ENABLED=false` and repeat the API request.

An illustrative successful local trace might show the following shape (these
numbers are examples, not measured project results):

| Stage | Example latency |
|---|---:|
| Guardrail | 180 ms |
| MCP wardrobe retrieval | 80 ms |
| Stylist generation | 1,070 ms |
| Style Critic | 410 ms |
| Validation and response formatting | 20 ms |
| Total | 1,760 ms |

Actual latency, token, and cost evidence must come from the configured Langfuse
project. The automated suite validates observation order and payloads with an
in-memory backend; it does not fabricate a hosted screenshot or paid-run data.

## Commands

```bash
uv run --project apps/backend pytest apps/backend/tests/test_observability.py
moon run backend:test
moon run frontend:build
moon run frontend:test
moon run :check
```
