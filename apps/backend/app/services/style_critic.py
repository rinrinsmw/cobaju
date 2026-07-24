"""Tool-free Style Critic sub-agent and deterministic recommendation validation."""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from agents import (
    Agent,
    AsyncOpenAI,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunHooks,
    Runner,
)
from agents.exceptions import AgentsException, ModelBehaviorError
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.observability import (
    Observability,
    agent_usage_details,
    finish_model_attempt,
    start_model_attempt,
)
from app.schemas.chat import StyleCriticEvaluation, StylistResponse
from app.services.stylist_agent import StylistAgentError


logger = logging.getLogger(__name__)


class StyleCriticError(StylistAgentError):
    """Raised when the critic cannot produce its structured verdict."""


class RecommendationValidationError(StylistAgentError):
    """Raised when a recommendation remains invalid after the allowed repair."""


class StyleCritic(Protocol):
    """Mockable boundary around the paid, tool-free critic call."""

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
        previous_outfit: StylistResponse | None = None,
    ) -> StyleCriticEvaluation: ...


@dataclass(frozen=True)
class DeterministicValidation:
    """Machine-checkable recommendation validation result."""

    violations: list[str]

    @property
    def accepted(self) -> bool:
        return not self.violations


_STYLE_CRITIC_INSTRUCTIONS = """
You are Cobaju's Style Critic sub-agent. You review one draft recommendation
and return structured evaluation only. You have no tools, must not call MCP,
must not generate a replacement recommendation, and never speak to the user.

Check only these responsibilities:
- every claimed owned item exists in owned_item_evidence;
- every required outfit category is represented by an owned item or explicit
  missing-category guidance;
- the draft matches the user's occasion;
- any refinement instruction in user_request was applied;
- explanations contain no claim unsupported by user_request or wardrobe evidence;
- when previous_outfit is supplied, the exact previous outfit is not repeated
  unless the request requires it.

Return exactly approved, issues, and repair_instruction. When approved, issues
and repair_instruction must both be empty. When rejected, give a short list of
specific issues and one concise, actionable repair instruction. Do not include
scores, rewritten copy, replacement item selections, or user-facing language.
""".strip()


class OpenAIAgentsStyleCritic:
    """Run one separate temperature-zero critic without wardrobe tools."""

    def __init__(
        self, settings: Settings, observability: Observability | None = None
    ) -> None:
        self.settings = settings
        self.observability = observability

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
        previous_outfit: StylistResponse | None = None,
    ) -> StyleCriticEvaluation:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        model_name = self.settings.resolved_style_critic_model
        if not api_key or not model_name:
            raise StyleCriticError("Style Critic model is not configured")

        evidence = [
            {
                "item_id": item.id,
                "name": item.name,
                "category": item.category.value,
                "color": item.color,
                "description": item.description,
            }
            for item in owned_item_evidence
        ]
        critic_input = json.dumps(
            {
                "user_request": user_request,
                "candidate": candidate.model_dump(mode="json"),
                "owned_item_evidence": evidence,
                "previous_outfit": (
                    previous_outfit.model_dump(mode="json")
                    if previous_outfit is not None
                    else None
                ),
            }
        )
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.openrouter_timeout_seconds,
        )
        model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        agent = Agent(
            name="Style Critic",
            instructions=_STYLE_CRITIC_INSTRUCTIONS,
            model=model,
            model_settings=ModelSettings(
                temperature=self.settings.style_critic_temperature,
                extra_body={"provider": {"require_parameters": True}},
            ),
            output_type=StyleCriticEvaluation,
        )

        try:
            for attempt in range(2):
                hooks = _CriticAttemptHooks()
                try:
                    result = await Runner.run(
                        agent,
                        critic_input,
                        max_turns=2,
                        hooks=hooks,
                        run_config=RunConfig(
                            tracing_disabled=True,
                            workflow_name="style_critic",
                            trace_include_sensitive_data=False,
                        ),
                    )
                    if not isinstance(result.final_output, StyleCriticEvaluation):
                        raise ModelBehaviorError(
                            "Style Critic returned invalid structured output"
                        )
                    break
                except ModelBehaviorError as error:
                    hooks.close(error)
                    if attempt == 0:
                        logger.warning(
                            "Style Critic returned malformed structured output; "
                            "retrying once"
                        )
                        continue
                    raise

            if self.observability is not None:
                self.observability.update_current(
                    usage_details=agent_usage_details(result),
                    metadata={
                        "prompt_version": (
                            self.settings.resolved_style_critic_prompt_version
                        )
                    },
                )
        except StyleCriticError:
            raise
        except AgentsException as error:
            hooks.close(error)
            raise StyleCriticError("Style Critic run failed") from error
        except Exception as error:
            hooks.close(error)
            logger.exception("Unexpected Style Critic failure")
            raise StyleCriticError("Style Critic run failed") from error
        finally:
            await client.close()

        return result.final_output


class _CriticAttemptHooks(RunHooks[None]):
    """Record each provider attempt, including one malformed-output retry."""

    def __init__(self) -> None:
        self.attempt_ids: list[str | None] = []

    async def on_llm_start(
        self, context: object, agent: object, system_prompt: object, input_items: object
    ) -> None:
        del context, agent, system_prompt, input_items
        self.attempt_ids.append(start_model_attempt("style_critic_model"))

    async def on_llm_end(
        self, context: object, agent: object, response: object
    ) -> None:
        del context, agent, response
        if self.attempt_ids:
            finish_model_attempt(self.attempt_ids.pop())

    def close(self, error: BaseException) -> None:
        while self.attempt_ids:
            finish_model_attempt(self.attempt_ids.pop(), error=error)


def get_owned_item_evidence(
    session: Session,
    user_id: int,
    candidate: StylistResponse,
) -> list[ClothingItem]:
    """Load only confirmed candidate items owned by the authenticated user."""

    item_ids = [item.item_id for item in candidate.owned_items]
    if not item_ids:
        return []
    statement = select(ClothingItem).where(
        ClothingItem.id.in_(item_ids),
        ClothingItem.user_id == user_id,
        ClothingItem.processing_status == ProcessingStatus.COMPLETED,
    )
    return list(session.exec(statement).all())


def validate_recommendation(
    candidate: StylistResponse,
    owned_item_evidence: list[ClothingItem],
) -> DeterministicValidation:
    """Apply unchanged ID, ownership, category, and missing-item checks."""

    evidence_by_id = {
        item.id: item for item in owned_item_evidence if item.id is not None
    }
    violations: list[str] = []
    for selected in candidate.owned_items:
        evidence = evidence_by_id.get(selected.item_id)
        if evidence is None:
            violations.append(
                "OWNED_OR_EXISTING_ITEM_ID_INVALID: "
                f"Item {selected.item_id} is not a confirmed item owned by this user."
            )
        elif selected.category != evidence.category:
            violations.append(
                f"ITEM_CATEGORY_UNSUPPORTED: Item {selected.item_id} has unsupported category "
                f"'{selected.category.value}'."
            )

    for missing in candidate.missing_categories:
        if not missing.guidance.casefold().startswith("not owned:"):
            violations.append(
                "MISSING_ITEM_LABEL_INVALID: "
                f"Missing {missing.category.value} guidance must start with 'Not owned:'."
            )

    required_categories = {
        required.category for required in candidate.required_categories
    }
    covered_categories = {
        selected.category for selected in candidate.owned_items
    } | {missing.category for missing in candidate.missing_categories}
    for category in required_categories - covered_categories:
        violations.append(
            f"REQUIRED_COMPONENT_MISSING: Required category '{category.value}' "
            "must have an owned item or explicit missing-category guidance."
        )
    return DeterministicValidation(violations=violations)
