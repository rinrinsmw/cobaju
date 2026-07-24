"""Phase 10 evaluator, hallucination validation, and repair tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio
import pytest
from agents.exceptions import ModelBehaviorError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings
from app.models.clothing_item import ClothingCategory, ClothingItem
from app.models.user import User
from app.schemas.chat import (
    ChatScopeDecision,
    MissingCategoryGuidance,
    StyleCriticEvaluation,
    RecommendedOwnedItem,
    RequiredCategory,
    StylistResponse,
)
from app.schemas.mcp import (
    GetStylingCandidatesOutput,
    SaveRecommendationOutput,
    StylingCandidateGroup,
    ToolClothingItem,
)
from app.services.chat import _grounding_violations, create_stylist_response
from app.services.outfit_evaluator import (
    RecommendationValidationError,
    get_owned_item_evidence,
    validate_recommendation,
)
from app.services.style_critic import OpenAIAgentsStyleCritic
from app.services.stylist_agent import (
    _REPAIR_INSTRUCTIONS,
    _STYLIST_INSTRUCTIONS,
    _ground_recommendation_prose,
    StylistLifecycleMetrics,
    StylistRunOutcome,
)


class AllowedClassifier:
    async def classify(self, message: str) -> ChatScopeDecision:
        return ChatScopeDecision(allowed=True, reason="fashion_request")


class SequencedRunner:
    def __init__(self, outcomes: list[StylistRunOutcome]) -> None:
        self.outcomes = outcomes
        self.feedback: list[str | None] = []
        self.run_calls = 0
        self.save_calls = 0
        self.session_count = 0
        self.metrics = StylistLifecycleMetrics(candidate_count=1, tool_call_count=1)

    @asynccontextmanager
    async def open_request(self, current_user: User) -> AsyncIterator["SequencedRunner"]:
        del current_user
        self.session_count += 1
        yield self

    async def run(
        self,
        message: str,
    ) -> StylistRunOutcome:
        del message
        self.run_calls += 1
        self.feedback.append(None)
        return self.outcomes[0]

    async def repair(
        self,
        message: str,
        candidate: StylistResponse,
        violations: list[str],
    ) -> StylistResponse:
        del message, candidate
        self.feedback.append(" ".join(violations))
        self.metrics.cache_reused_during_repair = True
        return self.outcomes[1].response

    async def save_recommendation(
        self, message: str, response: StylistResponse, evaluation_score: float
    ) -> SaveRecommendationOutput:
        del evaluation_score
        self.save_calls += 1
        self.metrics.tool_call_count += 1
        available = {item.item_id: item for item in self.outcomes[0].available_items}
        return SaveRecommendationOutput(
            user_request=message,
            items=[available[item.item_id] for item in response.owned_items],
            explanation=response.message,
            recommendation_id=1,
        )


class SequencedEvaluator:
    def __init__(self, evaluations: list[StyleCriticEvaluation]) -> None:
        self.evaluations = evaluations
        self.calls = 0

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
    ) -> StyleCriticEvaluation:
        del user_request, candidate, owned_item_evidence
        evaluation = self.evaluations[self.calls]
        self.calls += 1
        return evaluation


def evaluation(
    *,
    accepted: bool,
    feedback: str = "Looks good.",
    unsupported_claims: list[str] | None = None,
) -> StyleCriticEvaluation:
    issues = unsupported_claims or ([] if accepted else ["The draft needs repair."])
    return StyleCriticEvaluation(
        approved=accepted,
        issues=issues,
        repair_instruction="" if accepted else feedback,
    )


def candidate(
    item_id: int,
    *,
    category: ClothingCategory = ClothingCategory.TOP,
    missing_guidance: str | None = None,
) -> StylistResponse:
    return StylistResponse(
        status="recommendation",
        message="A simple office outfit.",
        required_categories=[
            RequiredCategory(category=ClothingCategory.TOP, reason="Office base")
        ],
        owned_items=[
            RecommendedOwnedItem(
                item_id=item_id,
                category=category,
                reason="Works for the requested outfit.",
            )
        ],
        missing_categories=(
            [
                MissingCategoryGuidance(
                    category=ClothingCategory.BOTTOM,
                    guidance=missing_guidance,
                )
            ]
            if missing_guidance
            else []
        ),
    )


def outcome(response: StylistResponse) -> StylistRunOutcome:
    return StylistRunOutcome(
        response=response,
        tool_names=["get_styling_candidates"],
        validated_item_ids=set(),
        available_items=[
            ToolClothingItem(
                item_id=10,
                name="Blue shirt",
                category=ClothingCategory.TOP,
                color="blue",
                description=None,
            )
        ],
        tool_invocation_counts={"get_styling_candidates": 1},
    )


def test_stylist_prompts_require_evidence_grounded_prose() -> None:
    assert "Ground every factual phrase" in _STYLIST_INSTRUCTIONS
    assert "does not prove its comfort" in _STYLIST_INSTRUCTIONS
    assert "If the evidence cannot support a detail, omit it" in _STYLIST_INSTRUCTIONS
    assert "Remove every unsupported claim named" in _REPAIR_INSTRUCTIONS
    assert "Keep warmth in the conversational phrasing" in _REPAIR_INSTRUCTIONS


def test_style_critic_retries_malformed_output_once_without_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_run(agent: object, *args: object, **kwargs: object) -> object:
        nonlocal calls
        del args, kwargs
        calls += 1
        assert getattr(agent, "tools") == []
        if calls == 1:
            raise ModelBehaviorError("malformed structured output")
        return SimpleNamespace(
            final_output=StyleCriticEvaluation(
                approved=True,
                issues=[],
                repair_instruction="",
            )
        )

    monkeypatch.setattr("app.services.style_critic.Runner.run", fake_run)
    critic = OpenAIAgentsStyleCritic(
        Settings(
            openrouter_api_key="test-key",
            openrouter_style_critic_model="critic-model",
        )
    )

    async def run() -> StyleCriticEvaluation:
        return await critic.evaluate(
            "Office outfit",
            candidate(10),
            [
                ClothingItem(
                    id=10,
                    user_id=1,
                    name="Blue shirt",
                    category=ClothingCategory.TOP,
                    color="blue",
                )
            ],
        )

    result = anyio.run(run)

    assert result.approved is True
    assert calls == 2


def test_stylist_free_text_is_rebuilt_from_cached_item_evidence() -> None:
    ungrounded = candidate(10)
    ungrounded.message = "This wrinkle-proof shirt keeps you comfortable."
    ungrounded.required_categories = []
    ungrounded.owned_items[0].reason = "Its silk fabric has a flattering fit."
    ungrounded.missing_categories = [
        MissingCategoryGuidance(
            category=ClothingCategory.BOTTOM,
            guidance="Not owned: add warm trousers.",
        )
    ]

    grounded = _ground_recommendation_prose(
        ungrounded, outcome(ungrounded).available_items
    )

    assert grounded.message == (
        "For your request, I’d pair your “Blue shirt”. "
        "This plan uses your blue top."
    )
    assert [required.category for required in grounded.required_categories] == [
        ClothingCategory.TOP,
        ClothingCategory.BOTTOM,
    ]
    assert [required.reason for required in grounded.required_categories] == [
        "I’d include a top in this outfit plan.",
        "I’d include a bottom in this outfit plan.",
    ]
    assert grounded.owned_items[0].reason == (
        "I’d use your blue top, “Blue shirt,” in this outfit plan."
    )
    assert grounded.missing_categories[0].guidance == (
        "Not owned: I’d add a bottom to this outfit plan."
    )
    assert "comfortable" not in grounded.model_dump_json()
    assert "silk" not in grounded.model_dump_json()


@pytest.fixture
def evaluation_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, email="owner@example.com", hashed_password="hash"))
        session.add(User(id=2, email="other@example.com", hashed_password="hash"))
        session.add(
            ClothingItem(
                id=10,
                user_id=1,
                name="Blue shirt",
                category=ClothingCategory.TOP,
                color="blue",
            )
        )
        session.add(
            ClothingItem(
                id=20,
                user_id=2,
                name="Other user's trousers",
                category=ClothingCategory.BOTTOM,
                color="black",
            )
        )
        session.commit()
        yield session


@pytest.mark.parametrize("item_id", [999, 20])
def test_invalid_and_cross_user_item_ids_are_blocked(
    evaluation_session: Session,
    item_id: int,
) -> None:
    response = candidate(item_id)
    evidence = get_owned_item_evidence(evaluation_session, 1, response)

    result = validate_recommendation(response, evidence)

    assert result.accepted is False
    assert "not a confirmed item owned by this user" in result.violations[0]


def test_unsupported_category_and_unlabelled_generic_advice_are_blocked(
    evaluation_session: Session,
) -> None:
    response = candidate(
        10,
        category=ClothingCategory.SHOES,
        missing_guidance="Add neutral trousers.",
    )
    evidence = get_owned_item_evidence(evaluation_session, 1, response)

    result = validate_recommendation(response, evidence)

    assert result.accepted is False
    assert any("unsupported category" in issue for issue in result.violations)
    assert any("must start with 'Not owned:'" in issue for issue in result.violations)


def test_cached_anchor_item_is_an_objective_blocking_requirement() -> None:
    response = candidate(10)
    run_outcome = outcome(response)
    anchor = ToolClothingItem(
        item_id=11,
        name="Black blazer",
        category=ClothingCategory.OUTERWEAR,
        color="black",
        description=None,
    )
    run_outcome.available_items.append(anchor)
    run_outcome.candidate_bundle = GetStylingCandidatesOutput(
        anchor_item=anchor,
        owned_item_ids=[10, 11],
        candidates_by_category=[
            StylingCandidateGroup(
                category=ClothingCategory.TOP,
                items=[run_outcome.available_items[0]],
            ),
            StylingCandidateGroup(
                category=ClothingCategory.OUTERWEAR,
                items=[anchor],
            ),
        ],
        missing_required_categories=[],
    )

    assert _grounding_violations(run_outcome) == ["ANCHOR_ITEM_MISSING: 11."]


def test_verified_unsupported_claim_triggers_one_successful_targeted_repair(
    evaluation_session: Session,
) -> None:
    response = candidate(10, missing_guidance="Not owned: add neutral trousers.")
    runner = SequencedRunner([outcome(response), outcome(response)])
    evaluator = SequencedEvaluator(
        [
            evaluation(
                accepted=False,
                feedback="Remove the unsupported fabric claim.",
                unsupported_claims=["The shirt is wrinkle-proof."],
            )
        ]
    )

    async def run() -> StylistResponse:
        return await create_stylist_response(
            message="Dress me for the office",
            current_user=User(
                id=1, email="owner@example.com", hashed_password="hash"
            ),
            classifier=AllowedClassifier(),
            runner=runner,
            evaluator=evaluator,
                settings=Settings(
                openrouter_stylist_model="stylist-model",
                openrouter_evaluator_model="evaluator-model",
            ),
        )

    result = anyio.run(run)

    assert result.model_dump(exclude={"lookbook_save_token"}) == response.model_dump()
    assert result.lookbook_save_token
    assert evaluator.calls == 1
    assert runner.run_calls == 1
    assert runner.feedback[0] is None
    assert "STYLE_CRITIC_ISSUE: The shirt is wrinkle-proof." in (
        runner.feedback[1] or ""
    )
    assert (
        "STYLE_CRITIC_REPAIR_INSTRUCTION: Remove the unsupported fabric claim."
        in (runner.feedback[1] or "")
    )


def test_deterministic_rejection_repairs_before_calling_evaluator(
    evaluation_session: Session,
) -> None:
    initial = candidate(10)
    initial.required_categories.append(
        RequiredCategory(
            category=ClothingCategory.BOTTOM,
            reason="A complete office outfit needs a bottom.",
        )
    )
    repaired = candidate(10, missing_guidance="Not owned: add neutral trousers.")
    repaired.required_categories.append(
        RequiredCategory(
            category=ClothingCategory.BOTTOM,
            reason="A complete office outfit needs a bottom.",
        )
    )
    runner = SequencedRunner([outcome(initial), outcome(repaired)])
    evaluator = SequencedEvaluator([evaluation(accepted=True)])

    async def run() -> StylistResponse:
        return await create_stylist_response(
            message="Dress me for the office",
            current_user=User(
                id=1, email="owner@example.com", hashed_password="hash"
            ),
            classifier=AllowedClassifier(),
            runner=runner,
            evaluator=evaluator,
                settings=Settings(
                openrouter_stylist_model="stylist-model",
                openrouter_evaluator_model="evaluator-model",
            ),
        )

    result = anyio.run(run)

    assert result.model_dump(exclude={"lookbook_save_token"}) == repaired.model_dump()
    assert result.lookbook_save_token
    assert runner.run_calls == 1
    assert evaluator.calls == 0
    assert "must have an owned item" in (runner.feedback[1] or "")


def test_valid_critic_rejection_repairs_once_without_rechecking_critic(
    evaluation_session: Session,
) -> None:
    response = candidate(10)
    runner = SequencedRunner([outcome(response), outcome(response)])
    evaluator = SequencedEvaluator(
        [
            evaluation(accepted=False, unsupported_claims=["Unsupported claim."]),
        ]
    )

    async def run() -> StylistResponse:
        return await create_stylist_response(
            message="Dress me for the office",
            current_user=User(
                id=1, email="owner@example.com", hashed_password="hash"
            ),
            classifier=AllowedClassifier(),
            runner=runner,
            evaluator=evaluator,
            settings=Settings(
                openrouter_stylist_model="stylist-model",
                openrouter_evaluator_model="evaluator-model",
            ),
        )

    result = anyio.run(run)

    assert result.status == "recommendation"
    assert evaluator.calls == 1
    assert runner.run_calls == 1
    assert len(runner.feedback) == 2
    assert "STYLE_CRITIC_ISSUE: Unsupported claim." in (runner.feedback[1] or "")
    assert runner.save_calls == 0
