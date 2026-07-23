"""Focused reliability tests for malformed stylist model output."""

import anyio
from agents.exceptions import ModelBehaviorError

from app.core.config import Settings
from app.schemas.chat import StylistResponse
from app.services import stylist_agent as stylist_agent_module
from app.services.stylist_agent import OpenAIAgentsStylistRunner


def test_malformed_structured_output_is_retried_once(
    monkeypatch,
) -> None:
    expected = StylistResponse(
        status="recommendation",
        message="Wear the relaxed option.",
        required_categories=[],
        owned_items=[],
        missing_categories=[],
    )
    calls = 0

    class Result:
        final_output = expected

    async def fake_run(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            raise ModelBehaviorError("truncated JSON")
        return Result()

    monkeypatch.setattr(stylist_agent_module.Runner, "run", fake_run)
    runner = OpenAIAgentsStylistRunner(
        Settings(
            openrouter_api_key="test-key",
            openrouter_stylist_model="test-model",
        )
    )

    async def run() -> StylistResponse:
        return await runner._generate(
            instructions="Return a recommendation.",
            model_input={"request": "More casual"},
            stage="stylist_model",
            temperature=0.5,
            prompt_version="test",
        )

    assert anyio.run(run) == expected
    assert calls == 2
