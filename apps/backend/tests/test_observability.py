"""Phase 13 tracing, metrics, tool, logging, and evaluation tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from typing import Any

import anyio
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings
from app.models.clothing_item import ClothingCategory, ClothingItem
from app.models.user import User
from app.observability import (
    LangfuseBackend,
    NoOpBackend,
    Observability,
    bind_authenticated_user,
    request_observability_middleware,
    structured_log,
)
from app.schemas.chat import (
    ChatScopeDecision,
    StyleCriticEvaluation,
    RecommendedOwnedItem,
    RequiredCategory,
    StylistResponse,
)
from app.schemas.mcp import SaveRecommendationOutput, ToolClothingItem
from app.services.chat import create_stylist_response
from app.services.chat_guardrails import OpenRouterChatScopeClassifier
from app.services.stylist_agent import (
    StylistAgentError,
    StylistLifecycleMetrics,
    StylistRunOutcome,
    ToolBudgetHooks,
)


class RecordedObservation:
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record
        self.trace_id = "trace-test-123"

    def update(self, **attributes: Any) -> None:
        self.record.setdefault("updates", []).append(attributes)

    def score_trace(self, *, name: str, value: float | str, comment: str = "") -> None:
        self.record.setdefault("scores", []).append(
            {"name": name, "value": value, "comment": comment}
        )

    def end(self) -> None:
        self.record["ended"] = True


class RecordingBackend:
    enabled = True

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.stack: list[RecordedObservation] = []

    @contextmanager
    def observe(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> Iterator[RecordedObservation]:
        record = {"name": name, "type": as_type, **attributes}
        observation = RecordedObservation(record)
        self.records.append(record)
        self.stack.append(observation)
        try:
            yield observation
            record["success"] = True
        except BaseException as error:
            record["success"] = False
            record["error_type"] = type(error).__name__
            raise
        finally:
            self.stack.pop()

    def current_trace_id(self) -> str | None:
        return self.stack[0].trace_id if self.stack else None

    def start_observation(
        self, name: str, *, as_type: str = "span", **attributes: Any
    ) -> RecordedObservation:
        record = {"name": name, "type": as_type, **attributes}
        observation = RecordedObservation(record)
        self.records.append(record)
        return observation

    def update_current(self, **attributes: Any) -> None:
        if self.stack:
            self.stack[-1].update(**attributes)


class AllowedClassifier:
    async def classify(self, message: str) -> ChatScopeDecision:
        del message
        return ChatScopeDecision(allowed=True, reason="fashion_request")


class PassingEvaluator:
    async def evaluate(
        self, user_request: str, candidate: StylistResponse, evidence: list[ClothingItem]
    ) -> StyleCriticEvaluation:
        del user_request, candidate, evidence
        return StyleCriticEvaluation(
            approved=True,
            issues=[],
            repair_instruction="",
        )


class LowSubjectiveEvaluator:
    async def evaluate(
        self, user_request: str, candidate: StylistResponse, evidence: list[ClothingItem]
    ) -> StyleCriticEvaluation:
        del user_request, candidate, evidence
        return StyleCriticEvaluation(
            approved=False,
            issues=["The outfit is not stylistically strong."],
            repair_instruction="Adjust the outfit to match the occasion.",
        )


def _response() -> StylistResponse:
    return StylistResponse(
        status="recommendation",
        message="Wear your blue shirt for a polished office base.",
        required_categories=[
            RequiredCategory(category=ClothingCategory.TOP, reason="Office base")
        ],
        owned_items=[
            RecommendedOwnedItem(
                item_id=10,
                category=ClothingCategory.TOP,
                reason="It matches the request.",
            )
        ],
        missing_categories=[],
    )


class ObservedRunner:
    def __init__(self, observability: Observability, *, fail: bool = False) -> None:
        self.observability = observability
        self.fail = fail
        self.metrics = StylistLifecycleMetrics(candidate_count=1, tool_call_count=1)

    @asynccontextmanager
    async def open_request(self, current_user: User) -> AsyncIterator["ObservedRunner"]:
        del current_user
        yield self

    async def run(
        self, message: str
    ) -> StylistRunOutcome:
        del message
        with self.observability.observe(
            "mcp.get_styling_candidates", as_type="tool"
        ):
            if self.fail:
                raise StylistAgentError("simulated failure")
        with self.observability.observe(
            "stylist_generation",
            as_type="generation",
            metadata={"prompt_version": "stylist-v2"},
        ):
            pass
        item = ToolClothingItem(
            item_id=10,
            name="Blue shirt",
            category=ClothingCategory.TOP,
            color="blue",
            description=None,
        )
        return StylistRunOutcome(
            response=_response(),
            tool_names=["get_styling_candidates"],
            validated_item_ids=set(),
            available_items=[item],
            tool_invocation_counts={"get_styling_candidates": 1},
            lifecycle_metrics=self.metrics,
        )

    async def repair(
        self,
        message: str,
        candidate: StylistResponse,
        violations: list[str],
    ) -> StylistResponse:
        del message, violations
        self.metrics.cache_reused_during_repair = True
        return candidate

    async def save_recommendation(
        self, message: str, response: StylistResponse, evaluation_score: float
    ) -> SaveRecommendationOutput:
        del evaluation_score
        self.metrics.tool_call_count += 1
        with self.observability.observe("mcp.save_recommendation", as_type="tool"):
            return SaveRecommendationOutput(
                user_request=message,
                items=[
                    ToolClothingItem(
                        item_id=10,
                        name="Blue shirt",
                        category=ClothingCategory.TOP,
                        color="blue",
                        description=None,
                    )
                ],
                explanation=response.message,
                recommendation_id=1,
            )


def _settings() -> Settings:
    return Settings(
        openrouter_chat_guardrail_model="guardrail-model",
        openrouter_stylist_model="stylist-model",
        openrouter_evaluator_model="evaluator-model",
        langfuse_enabled=False,
    )


def test_missing_credentials_disable_observability_without_failure() -> None:
    observability = Observability(
        Settings(
            langfuse_enabled=True,
            langfuse_public_key="",
            langfuse_secret_key="",
        )
    )

    assert isinstance(observability.backend, NoOpBackend)
    with observability.observe("safe_noop") as observation:
        assert observation is None


def test_langfuse_adapter_routes_usage_to_generation_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        def update_current_generation(self, **kwargs: Any) -> None:
            captured["generation"] = kwargs

        def update_current_span(self, **kwargs: Any) -> None:
            captured["span"] = kwargs

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    backend = LangfuseBackend(
        Settings(
            langfuse_public_key="public",
            langfuse_secret_key="secret",
        )
    )

    backend.update_current(usage_details={"input": 4, "output": 2, "total": 6})
    backend.update_current(output={"accepted": True})

    assert captured["generation"]["usage_details"]["total"] == 6
    assert captured["span"]["output"] == {"accepted": True}


def test_complete_stylist_trace_has_ordered_stages_metadata_counts_and_scores() -> None:
    backend = RecordingBackend()
    observability = Observability(_settings(), backend=backend)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    async def run() -> StylistResponse:
        with Session(engine) as session:
            user = User(id=1, email="trace@example.com", hashed_password="hash")
            session.add(user)
            session.add(
                ClothingItem(
                    id=10,
                    user_id=1,
                    name="Blue shirt",
                    category=ClothingCategory.TOP,
                    color="blue",
                )
            )
            session.commit()
            with observability.request_trace(
                request_id="request-123", endpoint="/chat/recommendations"
            ):
                bind_authenticated_user(1)
                return await create_stylist_response(
                    message="Office outfit",
                    current_user=user,
                    classifier=AllowedClassifier(),
                    runner=ObservedRunner(observability),
                    evaluator=PassingEvaluator(),
                        settings=_settings(),
                    observability=observability,
                )

    assert anyio.run(run).status == "recommendation"
    names = [record["name"] for record in backend.records]
    assert names == [
        "stylist_request",
        "guardrail.validate",
        "mcp.get_styling_candidates",
        "stylist_generation",
        "deterministic_validation",
        "style_critic",
        "response_formatting",
    ]
    agent = next(
        record for record in backend.records
        if record["name"] == "stylist_generation"
    )
    assert agent["metadata"]["prompt_version"] == "stylist-v2"
    formatting = backend.records[-1]["output"]
    assert formatting["tool_invocation_counts"] == {
        "get_styling_candidates": 1,
    }
    assert formatting["mcp_session_count"] == 1
    assert formatting["tool_call_count"] == 1
    assert formatting["candidate_count"] == 1
    root = backend.records[0]
    assert root["scores"][0]["name"] == "hallucination_detected"


def test_critic_rejection_records_one_targeted_repair() -> None:
    backend = RecordingBackend()
    observability = Observability(_settings(), backend=backend)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    async def run() -> StylistResponse:
        with Session(engine) as session:
            user = User(id=1, email="quality@example.com", hashed_password="hash")
            session.add(user)
            session.add(
                ClothingItem(
                    id=10,
                    user_id=1,
                    name="Blue shirt",
                    category=ClothingCategory.TOP,
                    color="blue",
                )
            )
            session.commit()
            with observability.request_trace(
                request_id="subjective-score", endpoint="/chat/recommendations"
            ):
                bind_authenticated_user(1)
                return await create_stylist_response(
                    message="Office outfit",
                    current_user=user,
                    classifier=AllowedClassifier(),
                    runner=ObservedRunner(observability),
                    evaluator=LowSubjectiveEvaluator(),
                    settings=_settings(),
                    observability=observability,
                )

    assert anyio.run(run).status == "recommendation"
    names = [record["name"] for record in backend.records]
    assert names.count("style_critic") == 1
    assert names.count("targeted_repair") == 1
    assert names.count("final_validation") == 1


def test_failed_tool_preserves_failed_span() -> None:
    backend = RecordingBackend()
    observability = Observability(_settings(), backend=backend)

    async def run() -> None:
        await ObservedRunner(observability, fail=True).run("request")

    with pytest.raises(StylistAgentError):
        anyio.run(run)

    assert backend.records[0]["name"] == "mcp.get_styling_candidates"
    assert backend.records[0]["success"] is False
    assert backend.records[0]["error_type"] == "StylistAgentError"


def test_tool_hooks_record_repeated_invocation_counts() -> None:
    backend = RecordingBackend()
    hooks = ToolBudgetHooks(
        maximum=3,
        observability=Observability(_settings(), backend=backend),
    )
    tool = type("Tool", (), {"name": "search_wardrobe"})()

    async def run() -> None:
        await hooks.on_tool_start(None, None, tool)
        await hooks.on_tool_end(None, None, tool, "{}")
        await hooks.on_tool_start(None, None, tool)
        await hooks.on_tool_end(None, None, tool, "{}")

    anyio.run(run)

    assert hooks.invocation_counts == {"search_wardrobe": 2}
    assert [record["metadata"]["invocation_number"] for record in backend.records] == [1, 2]
    assert all(record["ended"] for record in backend.records)


def test_structured_log_correlates_request_trace_and_hashed_user(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observability = Observability(_settings(), backend=RecordingBackend())

    with caplog.at_level("INFO", logger="app.requests"):
        with observability.request_trace(
            request_id="request-log", endpoint="/chat/recommendations"
        ):
            bind_authenticated_user(42)
            structured_log("request_completed", status=200, duration_ms=12.5)

    payload = json.loads(caplog.messages[-1])
    assert payload["request_id"] == "request-log"
    assert payload["trace_id"] == "trace-test-123"
    assert payload["user_id"] != "42"
    assert payload["status"] == 200


def test_request_middleware_logs_unhandled_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = SimpleNamespace(
        headers={"X-Request-ID": "exception-test"},
        url=SimpleNamespace(path="/test-error"),
    )

    async def call_next(_request: object) -> object:
        raise RuntimeError("simulated")

    async def run() -> None:
        await request_observability_middleware(request, call_next)

    with caplog.at_level("INFO"):
        with pytest.raises(RuntimeError, match="simulated"):
            anyio.run(run)

    payloads = [
        json.loads(message)
        for message in caplog.messages
        if message.startswith('{"event":')
    ]
    assert [payload["event"] for payload in payloads] == [
        "request_failed",
        "request_completed",
    ]
    assert payloads[0]["error_type"] == "RuntimeError"
    assert payloads[1]["status"] == 500


def test_style_critic_approval_has_empty_feedback() -> None:
    result = StyleCriticEvaluation(
        approved=True,
        issues=[],
        repair_instruction="",
    )

    assert result.model_dump() == {
        "approved": True,
        "issues": [],
        "repair_instruction": "",
    }


@pytest.mark.parametrize("reported_cost", [0.0042, None])
def test_guardrail_records_provider_tokens_and_only_provider_reported_cost(
    monkeypatch: pytest.MonkeyPatch, reported_cost: float | None
) -> None:
    backend = RecordingBackend()
    observability = Observability(_settings(), backend=backend)
    usage: dict[str, Any] = {
        "prompt_tokens": 40,
        "completion_tokens": 6,
        "total_tokens": 46,
    }
    if reported_cost is not None:
        usage["cost"] = reported_cost

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"allowed":true,"reason":"fashion_request"}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            }

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            del args, kwargs
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.chat_guardrails.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )
    classifier = OpenRouterChatScopeClassifier(
        Settings(
            openrouter_api_key="test-key",
            openrouter_chat_guardrail_model="guardrail-model",
        ),
        observability,
    )

    async def run() -> None:
        with observability.observe("guardrail", as_type="generation"):
            await classifier.classify("Help me dress for work")

    anyio.run(run)

    update = backend.records[0]["updates"][0]
    assert update["usage_details"] == {"input": 40, "output": 6, "total": 46}
    assert update["metadata"]["finish_reason"] == "stop"
    if reported_cost is None:
        assert "cost_details" not in update
    else:
        assert update["cost_details"] == {"total": reported_cost}
