"""Phase 10 evaluator, hallucination validation, and retry tests."""

import anyio
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings
from app.models.clothing_item import ClothingCategory, ClothingItem
from app.models.user import User
from app.schemas.chat import (
    ChatScopeDecision,
    MissingCategoryGuidance,
    OutfitEvaluation,
    RecommendedOwnedItem,
    RequiredCategory,
    StylistResponse,
)
from app.services.chat import create_stylist_response
from app.services.outfit_evaluator import (
    RecommendationValidationError,
    get_owned_item_evidence,
    validate_recommendation,
)
from app.services.stylist_agent import StylistRunOutcome


class AllowedClassifier:
    async def classify(self, message: str) -> ChatScopeDecision:
        return ChatScopeDecision(allowed=True, reason="fashion_request")


class SequencedRunner:
    def __init__(self, outcomes: list[StylistRunOutcome]) -> None:
        self.outcomes = outcomes
        self.feedback: list[str | None] = []

    async def run(
        self,
        message: str,
        current_user: User,
        feedback: str | None = None,
    ) -> StylistRunOutcome:
        del message, current_user
        self.feedback.append(feedback)
        return self.outcomes[len(self.feedback) - 1]


class SequencedEvaluator:
    def __init__(self, evaluations: list[OutfitEvaluation]) -> None:
        self.evaluations = evaluations
        self.calls = 0

    async def evaluate(
        self,
        user_request: str,
        candidate: StylistResponse,
        owned_item_evidence: list[ClothingItem],
    ) -> OutfitEvaluation:
        del user_request, candidate, owned_item_evidence
        evaluation = self.evaluations[self.calls]
        self.calls += 1
        return evaluation


def evaluation(*, accepted: bool, feedback: str = "Looks good.") -> OutfitEvaluation:
    return OutfitEvaluation(
        accepted=accepted,
        occasion_appropriate=accepted,
        complete=accepted,
        colors_compatible=accepted,
        styles_compatible=accepted,
        feedback=feedback,
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
        tool_names=["search_wardrobe", "save_recommendation"],
        validated_item_ids={item.item_id for item in response.owned_items},
    )


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


def test_evaluator_rejection_triggers_one_successful_retry(
    evaluation_session: Session,
) -> None:
    response = candidate(10, missing_guidance="Not owned: add neutral trousers.")
    runner = SequencedRunner([outcome(response), outcome(response)])
    evaluator = SequencedEvaluator(
        [
            evaluation(accepted=False, feedback="Improve outfit completeness."),
            evaluation(accepted=True),
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
            session=evaluation_session,
            settings=Settings(
                openrouter_stylist_model="stylist-model",
                openrouter_evaluator_model="evaluator-model",
            ),
        )

    result = anyio.run(run)

    assert result == response
    assert evaluator.calls == 2
    assert runner.feedback[0] is None
    assert "Evaluator rejected outfit completeness" in (runner.feedback[1] or "")


def test_stylist_retries_no_more_than_once(evaluation_session: Session) -> None:
    response = candidate(10)
    runner = SequencedRunner([outcome(response), outcome(response)])
    evaluator = SequencedEvaluator(
        [evaluation(accepted=False), evaluation(accepted=False)]
    )

    async def run() -> None:
        await create_stylist_response(
            message="Dress me for the office",
            current_user=User(
                id=1, email="owner@example.com", hashed_password="hash"
            ),
            classifier=AllowedClassifier(),
            runner=runner,
            evaluator=evaluator,
            session=evaluation_session,
            settings=Settings(
                openrouter_stylist_model="stylist-model",
                openrouter_evaluator_model="evaluator-model",
            ),
        )

    with pytest.raises(RecommendationValidationError):
        anyio.run(run)

    assert evaluator.calls == 2
    assert len(runner.feedback) == 2
