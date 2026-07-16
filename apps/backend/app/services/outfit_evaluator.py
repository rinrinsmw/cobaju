"""Phase 10 evaluator agent and deterministic recommendation validation."""

import json
from dataclasses import dataclass
from typing import Protocol

from agents import (
    Agent,
    AsyncOpenAI,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
)
from agents.exceptions import AgentsException
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.schemas.chat import OutfitEvaluation, StylistResponse
from app.services.stylist_agent import StylistAgentError


class OutfitEvaluatorError(StylistAgentError):
    """Raised when the evaluator cannot produce a structured verdict."""


class RecommendationValidationError(StylistAgentError):
    """Raised when a recommendation remains invalid after the allowed retry."""


class OutfitEvaluator(Protocol):
    """Mockable boundary around the paid evaluator call."""

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
    ) -> OutfitEvaluation: ...


@dataclass(frozen=True)
class DeterministicValidation:
    """Machine-checkable final validation result."""

    violations: list[str]

    @property
    def accepted(self) -> bool:
        return not self.violations


_EVALUATOR_INSTRUCTIONS = """
You are Cobaju's one Outfit Evaluator. Review the proposed outfit against the
user's occasion and the supplied database evidence. Check outfit completeness,
occasion relevance, color compatibility, style compatibility, and unsupported
claims. An item is owned only when it appears in owned_item_evidence. Generic
missing-item guidance is allowed only when it is explicitly labelled not owned.
An incomplete owned wardrobe may still pass completeness when the response
honestly identifies the gap and gives useful, clearly non-owned guidance.
Do not add items or rewrite the outfit. Return only the OutfitEvaluation schema.
Set accepted=true only when every check passes and unsupported_claims is empty.
Give concise correction feedback that a stylist can use for one retry.
""".strip()


class OpenAIAgentsOutfitEvaluator:
    """Run a separate temperature-zero evaluator without wardrobe tools."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
    ) -> OutfitEvaluation:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        model_name = self.settings.openrouter_evaluator_model
        if not api_key or not model_name:
            raise OutfitEvaluatorError("Evaluator model is not configured")

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
        evaluator_input = json.dumps(
            {
                "user_request": user_request,
                "candidate": candidate.model_dump(mode="json"),
                "owned_item_evidence": evidence,
            }
        )
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.openrouter_timeout_seconds,
        )
        model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        agent = Agent(
            name="Outfit Evaluator",
            instructions=_EVALUATOR_INSTRUCTIONS,
            model=model,
            model_settings=ModelSettings(
                temperature=self.settings.evaluator_temperature,
                extra_body={"provider": {"require_parameters": True}},
            ),
            output_type=OutfitEvaluation,
        )
        try:
            result = await Runner.run(
                agent,
                evaluator_input,
                max_turns=2,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name="outfit_evaluation",
                    trace_include_sensitive_data=False,
                ),
            )
        except AgentsException as error:
            raise OutfitEvaluatorError("Outfit evaluator run failed") from error
        finally:
            await client.close()

        evaluation = result.final_output
        if not isinstance(evaluation, OutfitEvaluation):
            raise OutfitEvaluatorError("Evaluator returned an invalid response")
        return evaluation


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
    """Apply final ID, ownership, category, and missing-item label checks."""

    evidence_by_id = {
        item.id: item for item in owned_item_evidence if item.id is not None
    }
    violations: list[str] = []
    for selected in candidate.owned_items:
        evidence = evidence_by_id.get(selected.item_id)
        if evidence is None:
            violations.append(
                f"Item {selected.item_id} is not a confirmed item owned by this user."
            )
        elif selected.category != evidence.category:
            violations.append(
                f"Item {selected.item_id} has unsupported category "
                f"'{selected.category.value}'."
            )

    for missing in candidate.missing_categories:
        if not missing.guidance.casefold().startswith("not owned:"):
            violations.append(
                f"Missing {missing.category.value} guidance must start with 'Not owned:'."
            )
    return DeterministicValidation(violations=violations)
