"""Tests for optional initial_message and staged chat planner validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from replicantx.models import (
    AuthConfig,
    AuthProvider,
    BrowserAction,
    BrowserConfig,
    BrowserObservation,
    InteractionMode,
    InteractiveElement,
    ReplicantConfig,
    ScenarioConfig,
    TestLevel as ScenarioLevel,
)
from replicantx.scenarios.browser_agent import BrowserScenarioRunner, PlannedAction


# ---------------------------------------------------------------------------
# Model-level: initial_message is now optional
# ---------------------------------------------------------------------------

def test_replicant_config_accepts_no_initial_message() -> None:
    config = ReplicantConfig(
        goal="Book a trip to Paris",
        interaction_mode=InteractionMode.BROWSER,
        browser=BrowserConfig(start_url="https://app.example.test"),
    )
    assert config.initial_message is None


def test_replicant_config_still_accepts_initial_message() -> None:
    config = ReplicantConfig(
        goal="Book a trip to Paris",
        initial_message="Hello, I'd like to book a trip.",
        interaction_mode=InteractionMode.BROWSER,
        browser=BrowserConfig(start_url="https://app.example.test"),
    )
    assert config.initial_message == "Hello, I'd like to book a trip."


# ---------------------------------------------------------------------------
# Planner validation: compose_chat and submit_chat
# ---------------------------------------------------------------------------

class StubAuth:
    async def authenticate(self) -> str:
        return ""

    async def get_headers(self) -> dict[str, str]:
        return {}


def _make_runner(initial_message: str | None = None) -> BrowserScenarioRunner:
    kwargs: dict = {
        "goal": "Book a trip",
        "interaction_mode": InteractionMode.BROWSER,
        "browser": BrowserConfig(start_url="https://app.example.test"),
    }
    if initial_message is not None:
        kwargs["initial_message"] = initial_message

    config = ScenarioConfig(
        name="Planner test",
        base_url="https://app.example.test",
        auth=AuthConfig(provider=AuthProvider.NOOP),
        level=ScenarioLevel.AGENT,
        replicant=ReplicantConfig(**kwargs),
    )
    return BrowserScenarioRunner(config, StubAuth())  # type: ignore[arg-type]


def test_normalize_planned_compose_chat_accepted() -> None:
    runner = _make_runner()
    runner.current_observation = BrowserObservation(
        url="https://app.example.test",
        title="Test",
        visible_text="",
        interactive_elements=[],
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
    )
    planned = PlannedAction(
        reasoning="Type mention before selecting from dropdown",
        action_type="compose_chat",
        value="Book a trip for @Charlie",
    )
    action, error = runner._normalize_planned_action(planned)
    assert error is None
    assert action is not None
    assert action.action_type == "compose_chat"
    assert action.value == "Book a trip for @Charlie"


def test_normalize_planned_compose_chat_requires_value() -> None:
    runner = _make_runner()
    runner.current_observation = BrowserObservation(
        url="https://app.example.test",
        title="Test",
        visible_text="",
        interactive_elements=[],
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
    )
    planned = PlannedAction(
        reasoning="Empty compose",
        action_type="compose_chat",
        value=None,
    )
    action, error = runner._normalize_planned_action(planned)
    assert action is None
    assert "compose_chat requires" in error


def test_normalize_planned_submit_chat_accepted() -> None:
    runner = _make_runner()
    runner.current_observation = BrowserObservation(
        url="https://app.example.test",
        title="Test",
        visible_text="",
        interactive_elements=[],
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
    )
    planned = PlannedAction(
        reasoning="Send the drafted message",
        action_type="submit_chat",
    )
    action, error = runner._normalize_planned_action(planned)
    assert error is None
    assert action is not None
    assert action.action_type == "submit_chat"


def test_planner_prompt_includes_staged_chat_actions() -> None:
    runner = _make_runner()
    prompt = runner._build_planner_system_prompt(initial_message_sent=False)
    assert "compose_chat" in prompt
    assert "submit_chat" in prompt


def test_planner_prompt_omits_initial_message_when_absent() -> None:
    runner = _make_runner(initial_message=None)
    prompt = runner._build_planner_system_prompt(initial_message_sent=False)
    assert "your first message should be" not in prompt


def test_planner_prompt_includes_initial_message_when_present() -> None:
    runner = _make_runner(initial_message="Book a trip for @Charlie")
    prompt = runner._build_planner_system_prompt(initial_message_sent=False)
    assert "Book a trip for @Charlie" in prompt
