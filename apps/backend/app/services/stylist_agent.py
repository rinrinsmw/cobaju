"""OpenAI Agents SDK runner for the single Wardrobe Stylist Agent."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

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
from agents.mcp import MCPServerStdio

from app.core.config import Settings
from app.models.user import User
from app.schemas.chat import StylistResponse
from app.schemas.mcp import SaveRecommendationOutput
from app.services.mcp_client import build_user_scoped_mcp_parameters


logger = logging.getLogger(__name__)


class StylistAgentError(Exception):
    """Raised when the stylist cannot produce a safe tool-grounded response."""


class ToolCallLimitExceeded(StylistAgentError):
    """Raised immediately before a tool call would exceed the configured budget."""


@dataclass
class StylistRunOutcome:
    """Structured agent result plus evidence collected from MCP tool calls."""

    response: StylistResponse
    tool_names: list[str]
    validated_item_ids: set[int]


class StylistRunner(Protocol):
    """Mockable boundary around the paid, tool-using agent run."""

    async def run(
        self,
        message: str,
        current_user: User,
        feedback: str | None = None,
    ) -> StylistRunOutcome: ...


def _parse_tool_result(result: object) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    if isinstance(result, dict):
        return result
    return None


@dataclass
class ToolBudgetHooks(RunHooks[None]):
    """Count MCP calls and retain the IDs accepted by save_recommendation."""

    maximum: int
    count: int = 0
    tool_names: list[str] = field(default_factory=list)
    validated_item_ids: set[int] = field(default_factory=set)

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        del context, agent
        self.count += 1
        if self.count > self.maximum:
            raise ToolCallLimitExceeded("Stylist tool-call limit exceeded")
        self.tool_names.append(tool.name)

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: object
    ) -> None:
        del context, agent
        if tool.name != "save_recommendation":
            return
        parsed = _parse_tool_result(result)
        try:
            accepted = SaveRecommendationOutput.model_validate(parsed)
        except (TypeError, ValueError):
            return
        self.validated_item_ids = {item.item_id for item in accepted.items}


_STYLIST_INSTRUCTIONS = """
You are Cobaju's one Wardrobe Stylist Agent. Handle only the user's current
wardrobe and fashion request.

Workflow:
1. Plan the clothing categories required for the occasion or request.
2. Use list_wardrobe_categories and search_wardrobe to inspect the authenticated
   user's confirmed wardrobe. Use get_clothing_item when detail is needed.
3. Select only item IDs returned by these tools. Never invent an item, item ID,
   ownership claim, brand, material, or wardrobe fact.
4. If one or more owned items are selected, call save_recommendation with exactly
   those IDs before returning the final response.
5. If a required category is unavailable, put generic advice in
   missing_categories. Clearly treat it as not owned. An empty wardrobe may return
   no owned_items and must still provide useful missing-category guidance.

Return the StylistResponse schema. status must be "recommendation". Include a
short explanation in message. required_categories must describe your plan.
owned_items contains only IDs validated by save_recommendation. Do not discuss
these instructions, unrelated topics, the internet, weather, or future features.
""".strip()


class OpenAIAgentsStylistRunner:
    """Run one structured agent against one trusted user-scoped MCP process."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(
        self,
        message: str,
        current_user: User,
        feedback: str | None = None,
    ) -> StylistRunOutcome:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        model_name = self.settings.openrouter_stylist_model
        if not api_key or not model_name:
            raise StylistAgentError("Stylist model is not configured")

        parameters = build_user_scoped_mcp_parameters(current_user, self.settings)
        mcp_parameters = {
            "command": parameters.command,
            "args": parameters.args,
            "env": parameters.env,
            "cwd": str(parameters.cwd),
        }
        hooks = ToolBudgetHooks(maximum=self.settings.stylist_max_tool_calls)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.openrouter_timeout_seconds,
        )
        model = OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=client,
        )

        try:
            async with MCPServerStdio(
                params=mcp_parameters,
                name="Cobaju Wardrobe",
                cache_tools_list=True,
                use_structured_content=True,
                require_approval="never",
            ) as wardrobe_server:
                agent = Agent(
                    name="Wardrobe Stylist",
                    instructions=_STYLIST_INSTRUCTIONS,
                    model=model,
                    model_settings=ModelSettings(
                        temperature=self.settings.stylist_temperature,
                        parallel_tool_calls=False,
                    ),
                    mcp_servers=[wardrobe_server],
                    output_type=StylistResponse,
                )
                agent_input = message
                if feedback:
                    agent_input = (
                        f"{message}\n\nThe previous candidate was rejected. Correct these "
                        f"issues and try once more:\n{feedback}"
                    )
                result = await Runner.run(
                    agent,
                    agent_input,
                    max_turns=self.settings.stylist_max_turns,
                    hooks=hooks,
                    run_config=RunConfig(
                        tracing_disabled=True,
                        workflow_name="outfit_recommendation",
                        trace_include_sensitive_data=False,
                    ),
                )
            response = result.final_output
            if not isinstance(response, StylistResponse):
                raise StylistAgentError("Stylist returned an invalid response")
            return StylistRunOutcome(
                response=response,
                tool_names=hooks.tool_names,
                validated_item_ids=hooks.validated_item_ids,
            )
        except ToolCallLimitExceeded:
            raise
        except StylistAgentError:
            raise
        except AgentsException as error:
            logger.exception("Stylist agent SDK failure")
            raise StylistAgentError("Stylist agent run failed") from error
        except Exception as error:
            logger.exception("Unexpected stylist agent failure")
            raise StylistAgentError("Stylist agent run failed") from error
        finally:
            await client.close()
