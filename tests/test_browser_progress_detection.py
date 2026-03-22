from __future__ import annotations

from datetime import datetime, timedelta, timezone

from replicantx.auth.base import AuthBase
from replicantx.models import (
    AuthConfig,
    AuthProvider,
    BrowserConfig,
    BrowserIdentityContext,
    BrowserObservation,
    BrowserScenarioDiagnostics,
    BrowserWebSocketEvent,
    InteractionMode,
    InteractiveElement,
    ReplicantConfig,
    ScenarioConfig,
    TestLevel as ScenarioLevel,
)
from replicantx.scenarios.browser_agent import BrowserScenarioRunner, PlannedAction


class StubAuthProvider(AuthBase):
    async def authenticate(self) -> str:
        return ""

    async def get_headers(self) -> dict[str, str]:
        return {}


class FakeWebSocket:
    def __init__(self, url: str):
        self.url = url
        self._handlers: dict[str, object] = {}

    def on(self, event_name: str, handler: object) -> None:
        self._handlers[event_name] = handler

    def emit(self, event_name: str, payload: object | None = None) -> None:
        handler = self._handlers[event_name]
        if payload is None:
            handler()  # type: ignore[misc]
        else:
            handler(payload)  # type: ignore[misc]


def _make_runner() -> BrowserScenarioRunner:
    config = ScenarioConfig(
        name="Progress detection",
        base_url="https://app.example.test",
        auth=AuthConfig(provider=AuthProvider.NOOP),
        level=ScenarioLevel.AGENT,
        replicant=ReplicantConfig(
            goal="Book a trip",
            initial_message="Book me a trip",
            interaction_mode=InteractionMode.BROWSER,
            browser=BrowserConfig(start_url="https://app.example.test/start"),
        ),
    )
    runner = BrowserScenarioRunner(config, StubAuthProvider(config.auth))
    runner.browser_diagnostics = BrowserScenarioDiagnostics(
        scenario_name=config.name,
        goal=config.replicant.goal,
        start_url=config.replicant.browser.start_url,
        started_at=datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc),
        identity=BrowserIdentityContext(),
    )
    return runner


def _wait_entry(
    timestamp: datetime,
    *,
    dom_changed: bool = False,
    had_activity: bool = False,
    page_signature: str = "same-page",
) -> dict[str, object]:
    return {
        "action": "wait",
        "detail": "",
        "success": True,
        "timestamp": timestamp,
        "dom_changed": dom_changed,
        "had_activity": had_activity,
        "page_signature": page_signature,
        "visible_text": "same text",
    }


def _make_observation(
    *,
    visible_text: str,
    elements: list[InteractiveElement],
) -> BrowserObservation:
    return BrowserObservation(
        url="https://app.example.test/trip",
        title="Trip",
        visible_text=visible_text,
        interactive_elements=elements,
        timestamp=datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc),
    )


def test_detect_stuck_loop_requires_quiet_wait_period() -> None:
    runner = _make_runner()
    start = datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc)
    runner.action_history = [
        _wait_entry(start + timedelta(seconds=index * 5))
        for index in range(6)
    ]

    assert runner._detect_stuck_loop() is True


def test_detect_stuck_loop_ignores_waits_with_recent_activity() -> None:
    runner = _make_runner()
    start = datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc)
    runner.action_history = [
        _wait_entry(
            start + timedelta(seconds=index * 5),
            had_activity=(index == 4),
        )
        for index in range(6)
    ]

    assert runner._detect_stuck_loop() is False


def test_detect_stuck_loop_triggers_on_repeated_failed_actions_without_progress() -> None:
    runner = _make_runner()
    start = datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc)
    runner.action_history = [
        {
            "action": "click",
            "detail": "element 25",
            "message": "Failed to click element 25: overlay intercepts pointer events",
            "success": False,
            "timestamp": start + timedelta(seconds=index * 5),
            "dom_changed": False,
            "had_activity": False,
            "page_signature": "same-page",
            "visible_text": "same text",
        }
        for index in range(3)
    ]

    assert runner._detect_stuck_loop() is True


def test_observation_change_detects_element_delta_even_when_text_matches() -> None:
    runner = _make_runner()
    before = _make_observation(
        visible_text="Searching flights for Paris",
        elements=[
            InteractiveElement(id="1", role="button", name="Cancel", tag_name="BUTTON"),
        ],
    )
    after = _make_observation(
        visible_text="Searching flights for Paris",
        elements=[
            InteractiveElement(id="1", role="button", name="Cancel", tag_name="BUTTON"),
            InteractiveElement(id="2", role="button", name="Select flight", tag_name="BUTTON"),
        ],
    )

    assert runner._observation_changed_meaningfully(before, after) is True


def test_record_websocket_tracks_first_party_activity() -> None:
    runner = _make_runner()
    websocket = FakeWebSocket("wss://app.example.test/realtime")

    runner._record_websocket(websocket)
    websocket.emit("framereceived", '{"status":"working"}')
    websocket.emit("close")

    assert runner.browser_diagnostics is not None
    assert [event.event_type for event in runner.browser_diagnostics.websocket_events] == [
        "open",
        "framereceived",
        "close",
    ]
    assert all(
        event.is_first_party for event in runner.browser_diagnostics.websocket_events
    )


def test_latest_turn_activity_timestamp_includes_websocket_events() -> None:
    runner = _make_runner()
    assert runner.browser_diagnostics is not None
    runner.browser_diagnostics.websocket_events.append(
        BrowserWebSocketEvent(
            event_type="framereceived",
            url="wss://app.example.test/realtime",
            is_first_party=True,
            timestamp=datetime(2026, 3, 22, 10, 1, tzinfo=timezone.utc),
        )
    )

    latest = runner._latest_turn_activity_timestamp(
        network_start=0,
        websocket_start=0,
    )

    assert latest == datetime(2026, 3, 22, 10, 1, tzinfo=timezone.utc)


def test_normalize_planned_action_rejects_non_numeric_target() -> None:
    runner = _make_runner()
    runner.current_observation = _make_observation(
        visible_text="Flight results",
        elements=[
            InteractiveElement(id="7", role="button", name="Select flight", tag_name="BUTTON"),
        ],
    )

    action, error = runner._normalize_planned_action(
        PlannedAction(
            reasoning="Select the flight",
            action_type="click",
            target="?",
        )
    )

    assert action is None
    assert error == "click requires a numeric element ID from the current elements list."


def test_normalize_planned_action_maps_scroll_value_to_direction() -> None:
    runner = _make_runner()

    action, error = runner._normalize_planned_action(
        PlannedAction(
            reasoning="Scroll down for more results",
            action_type="scroll",
            value="down",
        )
    )

    assert error is None
    assert action is not None
    assert action.action_type == "scroll"
    assert action.direction == "down"


def test_build_planner_recovery_guidance_flags_stale_dom_and_overlay_failures() -> None:
    runner = _make_runner()
    runner.action_history = [
        {
            "action": "click",
            "detail": "element 14",
            "message": "Failed to click element 14: target no longer exists in the DOM",
            "success": False,
        },
        {
            "action": "click",
            "detail": "element 22",
            "message": "Failed to click element 22: a visible overlay, modal, or drawer is blocking interaction",
            "success": False,
        },
    ]

    guidance = runner._build_planner_recovery_guidance()

    assert any("went stale" in hint for hint in guidance)
    assert any("overlay is likely blocking" in hint for hint in guidance)
