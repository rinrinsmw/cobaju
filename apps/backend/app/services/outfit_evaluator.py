"""Backward-compatible imports for the renamed Style Critic service."""

from app.services.style_critic import (
    DeterministicValidation,
    OpenAIAgentsStyleCritic,
    RecommendationValidationError,
    StyleCritic,
    StyleCriticError,
    get_owned_item_evidence,
    validate_recommendation,
)


# Keep old dependency/import names working while the implementation and trace
# identity are explicitly Style Critic.
OutfitEvaluator = StyleCritic
OutfitEvaluatorError = StyleCriticError
OpenAIAgentsOutfitEvaluator = OpenAIAgentsStyleCritic


__all__ = [
    "DeterministicValidation",
    "OpenAIAgentsOutfitEvaluator",
    "OpenAIAgentsStyleCritic",
    "OutfitEvaluator",
    "OutfitEvaluatorError",
    "RecommendationValidationError",
    "StyleCritic",
    "StyleCriticError",
    "get_owned_item_evidence",
    "validate_recommendation",
]
