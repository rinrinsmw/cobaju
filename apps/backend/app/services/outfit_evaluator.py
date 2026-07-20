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
    RunHooks,
    Runner,
)
from agents.exceptions import AgentsException
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.observability import (
    Observability,
    agent_usage_details,
    finish_model_attempt,
    start_model_attempt,
)
from app.schemas.chat import OutfitEvaluation, StylistResponse
from app.services.stylist_agent import StylistAgentError


class OutfitEvaluatorError(StylistAgentError):
    """Raised when the evaluator cannot produce a structured verdict."""


class RecommendationValidationError(StylistAgentError):
    """Raised when a recommendation remains invalid after the allowed repair."""


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


@dataclass(frozen=True)
class RecommendationQuality:
    """Lightweight, extensible quality checks for one final candidate."""

    only_owned_items: bool
    no_hallucinations: bool
    request_match: bool
    coherent_outfit: bool
    explanation_present: bool

    @property
    def passed(self) -> bool:
        return all(self.as_dict().values())

    def as_dict(self) -> dict[str, bool]:
        return {
            "only_owned_items": self.only_owned_items,
            "no_hallucinations": self.no_hallucinations,
            "request_match": self.request_match,
            "coherent_outfit": self.coherent_outfit,
            "explanation_present": self.explanation_present,
        }


_EVALUATOR_INSTRUCTIONS = """
You are Cobaju's one Outfit Evaluator. Review the proposed outfit against the
user's occasion and the supplied database evidence. Check outfit completeness,
occasion relevance, color compatibility, style compatibility, and unsupported
claims. Give the whole candidate an evaluation_score from 0 to 10. An item is
owned only when it appears in owned_item_evidence. Generic
missing-item guidance is allowed only when it is explicitly labelled not owned.
An incomplete owned wardrobe may still pass completeness when the response
honestly identifies the gap and gives useful, clearly non-owned guidance.
Do not add items or rewrite the outfit. Return only the OutfitEvaluation schema.
Set accepted=true only when every check passes and unsupported_claims is empty.
Give concise correction feedback that the targeted repair can apply once.
""".strip()


class OpenAIAgentsOutfitEvaluator:
    """Run a separate temperature-zero evaluator without wardrobe tools."""

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
        attempt_ids: list[str | None] = []

        class EvaluatorHooks(RunHooks[None]):
            async def on_llm_start(
                self, context: object, agent: object, system_prompt: object, input_items: object
            ) -> None:
                del context, agent, system_prompt, input_items
                attempt_ids.append(start_model_attempt("evaluator_model"))

            async def on_llm_end(
                self, context: object, agent: object, response: object
            ) -> None:
                del context, agent, response
                if attempt_ids:
                    finish_model_attempt(attempt_ids.pop())

        try:
            result = await Runner.run(
                agent,
                evaluator_input,
                max_turns=2,
                hooks=EvaluatorHooks(),
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name="outfit_evaluation",
                    trace_include_sensitive_data=False,
                ),
            )
            if self.observability is not None:
                self.observability.update_current(
                    usage_details=agent_usage_details(result),
                    metadata={"prompt_version": self.settings.evaluator_prompt_version},
                )
        except AgentsException as error:
            while attempt_ids:
                finish_model_attempt(attempt_ids.pop(), error=error)
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
            "must have an owned item or "
            "explicit missing-category guidance."
        )
    return DeterministicValidation(violations=violations)


def evaluate_recommendation_quality(
    candidate: StylistResponse,
    evaluation: OutfitEvaluation,
    deterministic: DeterministicValidation,
) -> RecommendationQuality:
    """Summarize semantic quality without comparing exact response wording."""

    ownership_violations = [
        violation
        for violation in deterministic.violations
        if "not a confirmed item owned" in violation
    ]
    return RecommendationQuality(
        only_owned_items=not ownership_violations,
        no_hallucinations=not evaluation.unsupported_claims
        and not ownership_violations,
        request_match=evaluation.occasion_appropriate,
        coherent_outfit=(
            evaluation.complete
            and evaluation.colors_compatible
            and evaluation.styles_compatible
        ),
        explanation_present=bool(candidate.message.strip()),
    )
