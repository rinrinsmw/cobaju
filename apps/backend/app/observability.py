"""Provider-neutral tracing, request correlation, and structured logging."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import traceback
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import Settings, get_settings


logger = logging.getLogger("app.requests")
logger.setLevel(logging.INFO)
telemetry_logger = logging.getLogger(__name__)


class Observation(Protocol):
    """Small observation API used by application services."""

    @property
    def trace_id(self) -> str | None: ...

    def update(self, **attributes: Any) -> None: ...

    def score_trace(self, *, name: str, value: float | str, comment: str = "") -> None: ...

    def end(self) -> None: ...


class TelemetryBackend(Protocol):
    """Adapter boundary for Langfuse or a future telemetry provider."""

    @property
    def enabled(self) -> bool: ...

    def observe(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> AbstractContextManager[Observation | None]: ...

    def start_observation(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> Observation | None: ...

    def current_trace_id(self) -> str | None: ...

    def update_current(self, **attributes: Any) -> None: ...


class NoOpBackend:
    """Keep all workflows operational when telemetry is disabled."""

    enabled = False

    def observe(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> AbstractContextManager[Observation | None]:
        del name, as_type, attributes
        return nullcontext()

    def current_trace_id(self) -> str | None:
        return None

    def start_observation(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> Observation | None:
        del name, as_type, attributes
        return None

    def update_current(self, **attributes: Any) -> None:
        del attributes


class LangfuseBackend:
    """The only module that knows about the Langfuse SDK."""

    enabled = True

    def __init__(self, settings: Settings) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=settings.langfuse_base_url,
            release=settings.app_version,
        )

    def observe(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> AbstractContextManager[Observation | None]:
        return self._client.start_as_current_observation(
            name=name, as_type=as_type, **attributes
        )

    def current_trace_id(self) -> str | None:
        return self._client.get_current_trace_id()

    def start_observation(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> Observation | None:
        return self._client.start_observation(
            name=name, as_type=as_type, **attributes
        )

    def update_current(self, **attributes: Any) -> None:
        generation_fields = {
            "completion_start_time",
            "model",
            "model_parameters",
            "usage_details",
            "cost_details",
            "prompt",
        }
        if generation_fields.intersection(attributes):
            self._client.update_current_generation(**attributes)
        else:
            self._client.update_current_span(**attributes)


@dataclass
class RequestContext:
    request_id: str
    endpoint: str
    trace_id: str | None = None
    user_id: str | None = None
    root_observation: Observation | None = None
    started_at: float = field(default_factory=time.perf_counter)
    failing_stage: str = "request"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model_attempts: list[dict[str, Any]] = field(default_factory=list)
    validation_failures: list[str] = field(default_factory=list)
    evaluator_failures: list[str] = field(default_factory=list)
    evaluator_scores: dict[str, bool | float | int] = field(default_factory=dict)
    workflow_tool_call_count: int = 0
    active_model_attempts: dict[str, tuple[float, dict[str, Any]]] = field(
        default_factory=dict
    )


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def current_request_context() -> RequestContext | None:
    return _request_context.get()


def bind_authenticated_user(user_id: int) -> None:
    """Attach a stable, non-reversible user reference to logs and traces."""

    context = current_request_context()
    if context is not None:
        context.user_id = user_observability_id(user_id)
        if context.root_observation is not None:
            context.root_observation.update(metadata={"user_id": context.user_id})


def user_observability_id(user_id: int) -> str:
    """Return the stable non-reversible user identifier used by telemetry."""

    return hashlib.sha256(f"cobaju-user:{user_id}".encode()).hexdigest()[:16]


def safe_request_id(value: str | None) -> str:
    """Accept simple correlation IDs and replace malformed values."""

    if value and len(value) <= 100 and all(
        character.isalnum() or character in "-_." for character in value
    ):
        return value
    return uuid.uuid4().hex


def structured_log(event: str, **fields: Any) -> None:
    """Emit one machine-readable JSON application log without secrets."""

    context = current_request_context()
    payload = {
        "event": event,
        "request_id": context.request_id if context else None,
        "trace_id": context.trace_id if context else None,
        "user_id": context.user_id if context else None,
        "endpoint": context.endpoint if context else None,
        **fields,
    }
    message = json.dumps(payload, separators=(",", ":"), default=str)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_parent_logger = logging.getLogger("uvicorn")
    # Uvicorn configures its own handlers and may leave the root logger without
    # one. Reuse its error logger in the running API, while keeping the normal
    # application logger available to tests and non-Uvicorn processes.
    target_logger = (
        uvicorn_logger
        if uvicorn_logger.handlers or uvicorn_parent_logger.handlers
        else logger
    )
    target_logger.info(message)


def set_failing_stage(stage: str) -> None:
    """Record the last request stage entered without exposing request content."""

    context = current_request_context()
    if context is not None:
        context.failing_stage = stage


def record_recommendation_diagnostics(
    *,
    validation_failures: list[str] | None = None,
    evaluator_failures: list[str] | None = None,
    evaluator_scores: dict[str, bool | float | int] | None = None,
    tool_call_count: int | None = None,
) -> None:
    """Retain only stable failure codes and schema-bounded evaluator scores."""

    context = current_request_context()
    if context is None:
        return
    if validation_failures is not None:
        context.validation_failures = list(validation_failures)
    if evaluator_failures is not None:
        context.evaluator_failures = list(evaluator_failures)
    if evaluator_scores is not None:
        context.evaluator_scores = dict(evaluator_scores)
    if tool_call_count is not None:
        context.workflow_tool_call_count = tool_call_count


def start_model_attempt(stage: str) -> str | None:
    """Start timing one real provider request."""

    context = current_request_context()
    if context is None:
        return None
    attempt_id = f"{stage}:{len(context.model_attempts) + 1}"
    record: dict[str, Any] = {
        "order": len(context.model_attempts) + 1,
        "stage": stage,
        "status": "started",
    }
    context.model_attempts.append(record)
    context.active_model_attempts[attempt_id] = (time.perf_counter(), record)
    return attempt_id


def finish_model_attempt(
    attempt_id: str | None, *, error: BaseException | None = None
) -> None:
    """Finish a provider-request timer and retain only safe diagnostic fields."""

    context = current_request_context()
    if context is None or attempt_id is None:
        return
    active = context.active_model_attempts.pop(attempt_id, None)
    if active is None:
        return
    started, record = active
    record.update(
        status="failed" if error else "completed",
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    if error is not None:
        record["error_type"] = type(error).__name__


def start_tool_call(name: str) -> dict[str, Any] | None:
    """Append one MCP call at start so parallel completion cannot reorder it."""

    context = current_request_context()
    if context is None:
        return None
    record: dict[str, Any] = {
        "order": len(context.tool_calls) + 1,
        "name": name,
        "status": "started",
    }
    context.tool_calls.append(record)
    return record


def finish_tool_call(
    record: dict[str, Any] | None, *, duration_ms: float, success: bool
) -> None:
    """Finish a previously registered sanitized MCP call record."""

    if record is not None:
        record.update(
            status="completed" if success else "failed",
            duration_ms=duration_ms,
            success=success,
        )


def stylist_failure_fields() -> dict[str, Any]:
    """Build the required sanitized failure payload from request-local state."""

    context = current_request_context()
    if context is None:
        return {
            "failing_stage": "unknown",
            "duration_ms": 0,
            "tool_call_count": 0,
            "model_attempt_count": 0,
            "validation_failures": [],
            "evaluator_failures": [],
            "evaluator_scores": {},
        }
    return {
        "failing_stage": context.failing_stage,
        "duration_ms": round((time.perf_counter() - context.started_at) * 1000, 2),
        "tool_call_count": max(
            len(context.tool_calls), context.workflow_tool_call_count
        ),
        "model_attempt_count": len(context.model_attempts),
        "tool_calls": context.tool_calls,
        "model_attempts": context.model_attempts,
        "validation_failures": context.validation_failures,
        "evaluator_failures": context.evaluator_failures,
        "evaluator_scores": context.evaluator_scores,
    }


def log_development_traceback(error: BaseException) -> None:
    """Print the complete traceback only for the local development environment."""

    if get_settings().app_environment != "development":
        return
    traceback_logger = logging.getLogger("uvicorn.error")
    traceback_logger.error(
        "Stylist request traceback (development only):\n%s",
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )


class Observability:
    """Application-facing observability facade with safe failure behavior."""

    def __init__(self, settings: Settings, backend: TelemetryBackend | None = None) -> None:
        self.settings = settings
        self.backend = backend or self._build_backend(settings)

    @staticmethod
    def _build_backend(settings: Settings) -> TelemetryBackend:
        if not settings.langfuse_enabled:
            return NoOpBackend()
        if (
            not settings.langfuse_public_key
            or not settings.langfuse_secret_key.get_secret_value()
        ):
            telemetry_logger.warning(
                "Langfuse is enabled but credentials are incomplete; observability is disabled"
            )
            return NoOpBackend()
        try:
            return LangfuseBackend(settings)
        except Exception:
            telemetry_logger.exception(
                "Langfuse initialization failed; observability is disabled"
            )
            return NoOpBackend()

    @property
    def enabled(self) -> bool:
        return self.backend.enabled

    def observe(
        self,
        name: str,
        *,
        as_type: str = "span",
        metadata: dict[str, Any] | None = None,
        **attributes: Any,
    ) -> AbstractContextManager[Observation | None]:
        common_metadata = {
            "application_version": self.settings.app_version,
            "provider": "openrouter",
        }
        context = current_request_context()
        if context:
            common_metadata.update(
                request_id=context.request_id,
                user_id=context.user_id,
            )
        common_metadata.update(metadata or {})
        try:
            return self.backend.observe(
                name, as_type=as_type, metadata=common_metadata, **attributes
            )
        except Exception:
            telemetry_logger.exception("Could not start telemetry observation %s", name)
            return nullcontext()

    def start_observation(
        self,
        name: str,
        *,
        as_type: str = "span",
        metadata: dict[str, Any] | None = None,
        **attributes: Any,
    ) -> Observation | None:
        """Start a span without attaching an async-context token.

        Tool hooks may start and finish in different asyncio contexts. A detached
        observation retains the current trace parent without requiring context
        detachment when the tool ends.
        """

        common_metadata = {
            "application_version": self.settings.app_version,
            "provider": "openrouter",
        }
        context = current_request_context()
        if context:
            common_metadata.update(
                request_id=context.request_id,
                user_id=context.user_id,
            )
        common_metadata.update(metadata or {})
        try:
            return self.backend.start_observation(
                name, as_type=as_type, metadata=common_metadata, **attributes
            )
        except Exception:
            telemetry_logger.exception("Could not start telemetry observation %s", name)
            return None

    @contextmanager
    def request_trace(
        self, *, request_id: str, endpoint: str
    ) -> Iterator[Observation | None]:
        context = RequestContext(request_id=request_id, endpoint=endpoint)
        token = _request_context.set(context)
        try:
            with self.observe(
                "stylist_request",
                as_type="chain",
                input={"endpoint": endpoint},
                metadata={"request_id": request_id},
            ) as observation:
                if observation is not None:
                    context.trace_id = observation.trace_id
                    context.root_observation = observation
                yield observation
        finally:
            _request_context.reset(token)

    def current_trace_id(self) -> str | None:
        try:
            return self.backend.current_trace_id()
        except Exception:
            return None

    def update_current(self, **attributes: Any) -> None:
        try:
            self.backend.update_current(**attributes)
        except Exception:
            telemetry_logger.exception("Could not update current telemetry observation")


def agent_usage_details(result: Any) -> dict[str, int]:
    """Aggregate token usage exposed by the Agents SDK without estimating cost."""

    responses = getattr(result, "raw_responses", [])
    return {
        "input": sum(
            getattr(response.usage, "input_tokens", 0) for response in responses
        ),
        "output": sum(
            getattr(response.usage, "output_tokens", 0) for response in responses
        ),
        "total": sum(
            getattr(response.usage, "total_tokens", 0) for response in responses
        ),
    }


@lru_cache
def get_observability() -> Observability:
    return Observability(get_settings())


async def request_observability_middleware(request: Any, call_next: Any) -> Any:
    """Correlate HTTP logs and the complete stylist trace."""

    observability = get_observability()
    request_id = safe_request_id(request.headers.get("X-Request-ID"))
    started = time.perf_counter()
    status_code = 500
    trace_context = (
        observability.request_trace(request_id=request_id, endpoint=request.url.path)
        if request.url.path == "/chat/recommendations"
        else _request_only_context(request_id, request.url.path)
    )
    with trace_context as root_observation:
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except BaseException as error:
            structured_log(
                "request_failed",
                status=500,
                error_type=type(error).__name__,
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            if root_observation is not None:
                root_observation.update(
                    output={"status": status_code},
                    level="ERROR" if status_code >= 500 else "DEFAULT",
                    status_message=(
                        f"HTTP {status_code}" if status_code >= 400 else None
                    ),
                    metadata={"duration_ms": duration_ms},
                )
            structured_log(
                "request_completed",
                status=status_code,
                duration_ms=duration_ms,
            )


@contextmanager
def _request_only_context(request_id: str, endpoint: str) -> Iterator[None]:
    token = _request_context.set(RequestContext(request_id=request_id, endpoint=endpoint))
    try:
        yield
    finally:
        _request_context.reset(token)
