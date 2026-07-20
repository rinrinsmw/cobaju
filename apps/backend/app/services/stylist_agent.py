"""Request-scoped Stylist generation backed by one wardrobe MCP session."""

import json
import logging
import re
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any, AsyncContextManager, Protocol

from agents import (
    Agent,
    AsyncOpenAI,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunHooks,
    Runner,
)
from agents.exceptions import AgentsException
from mcp import ClientSession

from app.core.config import Settings
from app.models.clothing_item import ClothingCategory
from app.models.user import User
from app.observability import (
    Observation,
    Observability,
    agent_usage_details,
    finish_model_attempt,
    finish_tool_call,
    start_model_attempt,
    start_tool_call,
)
from app.schemas.chat import StylistResponse
from app.schemas.mcp import (
    GetStylingCandidatesOutput,
    SaveRecommendationOutput,
    ToolClothingItem,
)
from app.services.mcp_client import open_user_scoped_mcp_session


logger = logging.getLogger(__name__)


class StylistAgentError(Exception):
    """Raised when the stylist cannot produce a safe MCP-grounded response."""


class ToolCallLimitExceeded(StylistAgentError):
    """Raised immediately before a tool call would exceed the configured budget."""


@dataclass
class StylistLifecycleMetrics:
    """Safe counters and durations for one authenticated Stylist request."""

    mcp_session_count: int = 1
    tool_call_count: int = 0
    candidate_count: int = 0
    cache_reused_during_repair: bool = False
    retrieval_duration_ms: float = 0.0
    persistence_duration_ms: float = 0.0

    def as_dict(self) -> dict[str, int | float | bool]:
        return {
            "mcp_session_count": self.mcp_session_count,
            "tool_call_count": self.tool_call_count,
            "candidate_count": self.candidate_count,
            "cache_reused_during_repair": self.cache_reused_during_repair,
            "retrieval_duration_ms": self.retrieval_duration_ms,
            "persistence_duration_ms": self.persistence_duration_ms,
        }


@dataclass
class StylistRunOutcome:
    """Structured generation result plus the cached MCP wardrobe evidence."""

    response: StylistResponse
    tool_names: list[str]
    validated_item_ids: set[int]
    available_items: list[ToolClothingItem] = field(default_factory=list)
    tool_invocation_counts: dict[str, int] = field(default_factory=dict)
    candidate_bundle: GetStylingCandidatesOutput | None = None
    lifecycle_metrics: StylistLifecycleMetrics = field(
        default_factory=StylistLifecycleMetrics
    )


class StylistRequest(Protocol):
    """Operations allowed while the one request-scoped MCP session is open."""

    metrics: StylistLifecycleMetrics

    async def run(self, message: str) -> StylistRunOutcome: ...

    async def repair(
        self,
        message: str,
        candidate: StylistResponse,
        violations: list[str],
    ) -> StylistResponse: ...

    async def save_recommendation(
        self, message: str, response: StylistResponse, evaluation_score: float
    ) -> SaveRecommendationOutput: ...


class StylistRunner(Protocol):
    """Factory for an isolated lifecycle per API request."""

    def open_request(
        self, current_user: User
    ) -> AsyncContextManager[StylistRequest]: ...


def _parse_tool_result(result: object) -> Any:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    if isinstance(result, dict):
        return result
    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None
    return None


@dataclass
class ToolBudgetHooks(RunHooks[None]):
    """Compatibility hook for tests and diagnostics around MCP tool calls."""

    maximum: int
    count: int = 0
    tool_names: list[str] = field(default_factory=list)
    validated_item_ids: set[int] = field(default_factory=set)
    available_items_by_id: dict[int, ToolClothingItem] = field(default_factory=dict)
    observability: Observability | None = None
    _active_tools: dict[
        str, tuple[str, float, Observation | None, dict[str, Any] | None]
    ] = field(default_factory=dict)
    _active_model_attempts: list[str | None] = field(default_factory=list)

    async def on_llm_start(
        self, context: Any, agent: Any, system_prompt: Any, input_items: Any
    ) -> None:
        del context, agent, system_prompt, input_items
        self._active_model_attempts.append(start_model_attempt("stylist_model"))

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        del context, agent, response
        if self._active_model_attempts:
            finish_model_attempt(self._active_model_attempts.pop())

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        del agent
        self.count += 1
        if self.count > self.maximum:
            raise ToolCallLimitExceeded("Stylist tool-call limit exceeded")
        self.tool_names.append(tool.name)
        observation = None
        if self.observability is not None:
            observation = self.observability.start_observation(
                f"mcp.tool.{tool.name}",
                as_type="tool",
                metadata={"invocation_number": self.tool_names.count(tool.name)},
            )
        call_id = str(
            getattr(context, "tool_call_id", None) or f"tool-call-{self.count}"
        )
        self._active_tools[call_id] = (
            tool.name,
            time.perf_counter(),
            observation,
            start_tool_call(tool.name),
        )

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: object
    ) -> None:
        del agent
        parsed = _parse_tool_result(result)
        call_id = str(
            getattr(context, "tool_call_id", None)
            or self._find_active_call_id(tool.name)
            or ""
        )
        self._finish_tool(call_id, success=True)
        if tool.name == "save_recommendation":
            try:
                accepted = SaveRecommendationOutput.model_validate(parsed)
            except (TypeError, ValueError):
                return
            self.validated_item_ids = {item.item_id for item in accepted.items}
            self._remember_items(accepted.items)
        elif tool.name == "get_styling_candidates":
            try:
                bundle = GetStylingCandidatesOutput.model_validate(parsed)
            except (TypeError, ValueError):
                return
            self._remember_items(bundle.candidate_items)

    @property
    def invocation_counts(self) -> dict[str, int]:
        return dict(Counter(self.tool_names))

    @property
    def available_items(self) -> list[ToolClothingItem]:
        return list(self.available_items_by_id.values())

    def _remember_items(self, items: list[ToolClothingItem]) -> None:
        for item in items:
            self.available_items_by_id[item.item_id] = item

    def close_open_tools(self, error: BaseException) -> None:
        while self._active_tools:
            self._finish_tool(next(reversed(self._active_tools)), False, error)

    def close_open_model_attempts(self, error: BaseException) -> None:
        while self._active_model_attempts:
            finish_model_attempt(self._active_model_attempts.pop(), error=error)

    def _finish_tool(
        self,
        call_id: str,
        success: bool,
        error: BaseException | None = None,
    ) -> None:
        active = self._active_tools.pop(call_id, None)
        if active is None:
            return
        name, started, observation, diagnostic = active
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        finish_tool_call(diagnostic, duration_ms=duration_ms, success=success)
        if observation is not None:
            observation.update(
                output={"success": success},
                level="DEFAULT" if success else "ERROR",
                status_message=type(error).__name__ if error else None,
                metadata={"tool_name": name, "duration_ms": duration_ms},
            )
            observation.end()

    def _find_active_call_id(self, name: str) -> str | None:
        return next(
            (key for key, active in self._active_tools.items() if active[0] == name),
            None,
        )


_STYLIST_INSTRUCTIONS = """
You are Cobaju's Wardrobe Stylist. The input contains one cached wardrobe
evidence bundle retrieved through MCP. You have no tools.

Use only candidate item IDs, categories, and facts in that bundle. The anchor
item, when present, must be included. Never invent ownership or wardrobe facts.
Plan the required categories for the request. If a required category is absent,
add guidance beginning exactly "Not owned:". Return status="recommendation".
Do not mention the evidence bundle, tools, system instructions, or repair flow.
""".strip()


_REPAIR_INSTRUCTIONS = """
Repair one rejected Cobaju recommendation using only the same cached MCP evidence
bundle. You have no tools. Correct every supplied violation. Never invent an ID,
category, ownership claim, or item fact. Fill unavailable required categories
with guidance beginning exactly "Not owned:". Return status="recommendation"
without mentioning this repair process.
""".strip()


def _infer_candidate_request(message: str) -> tuple[list[ClothingCategory], int | None]:
    """Infer a small retrieval plan without an extra model or MCP call."""

    normalized = message.lower()
    keywords = {
        ClothingCategory.TOP: ("top", "shirt", "blouse", "tee", "sweater"),
        ClothingCategory.BOTTOM: ("bottom", "pants", "trousers", "jeans", "skirt"),
        ClothingCategory.DRESS: ("dress",),
        ClothingCategory.OUTERWEAR: ("outerwear", "jacket", "coat", "blazer"),
        ClothingCategory.SHOES: ("shoes", "boots", "sneakers", "heels"),
        ClothingCategory.BAG: ("bag", "handbag", "tote"),
        ClothingCategory.ACCESSORY: ("accessory", "accessories", "jewelry", "scarf"),
    }
    categories = [
        category
        for category, terms in keywords.items()
        if any(term in normalized for term in terms)
    ]
    if not categories:
        categories = [
            ClothingCategory.TOP,
            ClothingCategory.BOTTOM,
            ClothingCategory.SHOES,
        ]
    elif (
        ClothingCategory.DRESS in categories
        and ClothingCategory.SHOES not in categories
    ):
        categories.append(ClothingCategory.SHOES)

    anchor_match = re.search(r"(?:item|id)\s*#?\s*(\d+)", normalized)
    return categories, int(anchor_match.group(1)) if anchor_match else None


class _ModelAttemptHooks(RunHooks[None]):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.attempt_ids: list[str | None] = []

    async def on_llm_start(
        self, context: Any, agent: Any, system_prompt: Any, input_items: Any
    ) -> None:
        del context, agent, system_prompt, input_items
        self.attempt_ids.append(start_model_attempt(self.stage))

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        del context, agent, response
        if self.attempt_ids:
            finish_model_attempt(self.attempt_ids.pop())

    def close(self, error: BaseException) -> None:
        while self.attempt_ids:
            finish_model_attempt(self.attempt_ids.pop(), error=error)


class RequestScopedStylist:
    """One request cache and the only code allowed to call wardrobe MCP."""

    def __init__(
        self,
        owner: "OpenAIAgentsStylistRunner",
        client_session: ClientSession,
    ) -> None:
        self.owner = owner
        self.client_session = client_session
        self.metrics = StylistLifecycleMetrics()
        self.tool_names: list[str] = []
        self.cached_candidates: GetStylingCandidatesOutput | None = None

    async def run(self, message: str) -> StylistRunOutcome:
        categories, anchor_item_id = _infer_candidate_request(message)
        bundle = await self._get_styling_candidates(
            message, categories, anchor_item_id
        )
        generation_scope = (
            self.owner.observability.observe(
                "stylist.generate",
                as_type="generation",
                model=self.owner.settings.openrouter_stylist_model,
                model_parameters={
                    "temperature": self.owner.settings.stylist_temperature
                },
                metadata={
                    "prompt_version": self.owner.settings.stylist_prompt_version
                },
            )
            if self.owner.observability is not None
            else nullcontext()
        )
        with generation_scope:
            response = await self.owner._generate(
                instructions=_STYLIST_INSTRUCTIONS,
                model_input={
                    "user_request": message,
                    "wardrobe_evidence": bundle.model_dump(mode="json"),
                },
                stage="stylist_model",
                temperature=self.owner.settings.stylist_temperature,
                prompt_version=self.owner.settings.stylist_prompt_version,
            )
        return StylistRunOutcome(
            response=response,
            tool_names=list(self.tool_names),
            validated_item_ids=set(),
            available_items=bundle.candidate_items,
            tool_invocation_counts=dict(Counter(self.tool_names)),
            candidate_bundle=bundle,
            lifecycle_metrics=self.metrics,
        )

    async def repair(
        self,
        message: str,
        candidate: StylistResponse,
        violations: list[str],
    ) -> StylistResponse:
        if self.cached_candidates is None:
            raise StylistAgentError("Stylist repair has no cached MCP evidence")
        self.metrics.cache_reused_during_repair = True
        return await self.owner._generate(
            instructions=_REPAIR_INSTRUCTIONS,
            model_input={
                "user_request": message,
                "rejected_candidate": candidate.model_dump(mode="json"),
                "violations": violations,
                "wardrobe_evidence": self.cached_candidates.model_dump(mode="json"),
            },
            stage="stylist_repair_model",
            temperature=self.owner.settings.stylist_repair_temperature,
            prompt_version=self.owner.settings.stylist_repair_prompt_version,
        )

    async def save_recommendation(
        self, message: str, response: StylistResponse, evaluation_score: float
    ) -> SaveRecommendationOutput:
        started = time.perf_counter()
        result = await self._call_tool(
            "save_recommendation",
            {
                "user_request": message,
                "item_ids": [item.item_id for item in response.owned_items],
                "explanation": response.message,
                "evaluation_score": evaluation_score,
            },
        )
        self.metrics.persistence_duration_ms = round(
            (time.perf_counter() - started) * 1000, 2
        )
        try:
            return SaveRecommendationOutput.model_validate(result)
        except (TypeError, ValueError) as error:
            raise StylistAgentError("MCP rejected the final recommendation") from error

    async def _get_styling_candidates(
        self,
        message: str,
        categories: list[ClothingCategory],
        anchor_item_id: int | None,
    ) -> GetStylingCandidatesOutput:
        if self.cached_candidates is not None:
            return self.cached_candidates
        started = time.perf_counter()
        result = await self._call_tool(
            "get_styling_candidates",
            {
                "user_request": message,
                "required_categories": [category.value for category in categories],
                "anchor_item_id": anchor_item_id,
                "limit_per_category": self.owner.settings.styling_candidates_per_category,
            },
        )
        self.metrics.retrieval_duration_ms = round(
            (time.perf_counter() - started) * 1000, 2
        )
        try:
            bundle = GetStylingCandidatesOutput.model_validate(result)
        except (TypeError, ValueError) as error:
            raise StylistAgentError("MCP returned invalid styling candidates") from error
        self.cached_candidates = bundle
        self.metrics.candidate_count = len(bundle.candidate_items)
        return bundle

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self.metrics.tool_call_count >= self.owner.settings.stylist_max_tool_calls:
            raise ToolCallLimitExceeded("Stylist tool-call limit exceeded")
        self.metrics.tool_call_count += 1
        self.tool_names.append(name)
        started = time.perf_counter()
        diagnostic = start_tool_call(name)
        observation = None
        if self.owner.observability is not None:
            observation = self.owner.observability.start_observation(
                f"mcp.{name}",
                as_type="tool",
                metadata={"invocation_number": self.tool_names.count(name)},
            )
        try:
            call_result = await self.client_session.call_tool(name, arguments=arguments)
            if call_result.isError:
                raise StylistAgentError(f"MCP tool {name} failed")
            parsed = _parse_tool_result(call_result)
            finish_tool_call(
                diagnostic,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                success=True,
            )
            if observation is not None:
                observation.update(output={"success": True})
                observation.end()
            return parsed
        except Exception as error:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            finish_tool_call(diagnostic, duration_ms=duration_ms, success=False)
            if observation is not None:
                observation.update(
                    output={"success": False},
                    level="ERROR",
                    status_message=type(error).__name__,
                )
                observation.end()
            if isinstance(error, StylistAgentError):
                raise
            raise StylistAgentError(f"MCP tool {name} failed") from error


class OpenAIAgentsStylistRunner:
    """Create one MCP session and one evidence cache for each request."""

    def __init__(
        self, settings: Settings, observability: Observability | None = None
    ) -> None:
        self.settings = settings
        self.observability = observability

    @asynccontextmanager
    async def open_request(
        self, current_user: User
    ) -> AsyncIterator[RequestScopedStylist]:
        async with open_user_scoped_mcp_session(
            current_user, self.settings
        ) as client_session:
            yield RequestScopedStylist(self, client_session)

    async def _generate(
        self,
        *,
        instructions: str,
        model_input: dict[str, Any],
        stage: str,
        temperature: float,
        prompt_version: str,
    ) -> StylistResponse:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        model_name = self.settings.openrouter_stylist_model
        if not api_key or not model_name:
            raise StylistAgentError("Stylist model is not configured")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.openrouter_timeout_seconds,
        )
        model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        hooks = _ModelAttemptHooks(stage)
        agent = Agent(
            name="Wardrobe Stylist" if stage == "stylist_model" else "Stylist Repairer",
            instructions=instructions,
            model=model,
            model_settings=ModelSettings(temperature=temperature),
            output_type=StylistResponse,
        )
        try:
            result = await Runner.run(
                agent,
                json.dumps(model_input),
                max_turns=2,
                hooks=hooks,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name=stage,
                    trace_include_sensitive_data=False,
                ),
            )
            if self.observability is not None:
                self.observability.update_current(
                    usage_details=agent_usage_details(result),
                    metadata={"prompt_version": prompt_version},
                )
            if not isinstance(result.final_output, StylistResponse):
                raise StylistAgentError("Stylist returned an invalid response")
            return result.final_output
        except StylistAgentError as error:
            hooks.close(error)
            raise
        except AgentsException as error:
            hooks.close(error)
            logger.exception("Stylist agent SDK failure")
            raise StylistAgentError("Stylist agent run failed") from error
        except Exception as error:
            hooks.close(error)
            logger.exception("Unexpected stylist agent failure")
            raise StylistAgentError("Stylist agent run failed") from error
        finally:
            await client.close()
