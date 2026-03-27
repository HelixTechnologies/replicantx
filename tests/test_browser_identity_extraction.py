from __future__ import annotations

from datetime import datetime, timezone

import pytest

from replicantx.auth.base import AuthBase
from replicantx.models import (
    AuthConfig,
    AuthProvider,
    BrowserConfig,
    BrowserIdentityContext,
    BrowserScenarioDiagnostics,
    InteractionMode,
    ReplicantConfig,
    ScenarioConfig,
    TestLevel as ScenarioLevel,
)
from replicantx.scenarios.browser_agent import BrowserScenarioRunner


class StubAuthProvider(AuthBase):
    async def authenticate(self) -> str:
        return ""

    async def get_headers(self) -> dict[str, str]:
        return {}


class FakeResponse:
    def __init__(self, status: int, payload: dict[str, object]):
        self.status = status
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return self._payload


class FakeRequestApi:
    def __init__(self, response: FakeResponse):
        self._response = response

    async def get(self, url: str) -> FakeResponse:
        return self._response


class FakeContext:
    def __init__(self, cookies: list[dict[str, object]], response: FakeResponse):
        self._cookies = cookies
        self.request = FakeRequestApi(response)

    async def cookies(self) -> list[dict[str, object]]:
        return self._cookies


class FakePage:
    def __init__(self, storage_result: dict[str, object] | None = None, *, raise_on_evaluate: bool = False):
        self._storage_result = storage_result or {}
        self._raise_on_evaluate = raise_on_evaluate

    async def evaluate(self, script: str) -> dict[str, object]:
        if self._raise_on_evaluate:
            raise RuntimeError("localStorage unavailable")
        return self._storage_result


class FakeBrowserDriver:
    def __init__(self, page: FakePage, context: FakeContext):
        self._page = page
        self._context = context

    def get_page(self) -> FakePage:
        return self._page

    def get_context(self) -> FakeContext:
        return self._context


def _make_runner() -> BrowserScenarioRunner:
    config = ScenarioConfig(
        name="Identity extraction",
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
        started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
        identity=BrowserIdentityContext(),
    )
    return runner


@pytest.mark.asyncio
async def test_refresh_identity_context_prefers_local_storage() -> None:
    runner = _make_runner()
    runner.browser_driver = FakeBrowserDriver(
        page=FakePage({"userId": "user-1", "conversationId": "conv-1"}),
        context=FakeContext([], FakeResponse(404, {})),
    )

    await runner._refresh_identity_context()

    assert runner.browser_diagnostics is not None
    assert runner.browser_diagnostics.identity.user_id == "user-1"
    assert runner.browser_diagnostics.identity.conversation_id == "conv-1"
    assert runner.browser_diagnostics.identity.extraction_source == "local_storage"


@pytest.mark.asyncio
async def test_refresh_identity_context_uses_cookies_when_storage_missing() -> None:
    runner = _make_runner()
    runner.browser_driver = FakeBrowserDriver(
        page=FakePage({}),
        context=FakeContext(
            [
                {"name": "helix_authenticated_user_id", "value": "user-cookie"},
                {"name": "conversationId", "value": "conv-cookie"},
            ],
            FakeResponse(404, {}),
        ),
    )

    await runner._refresh_identity_context()

    assert runner.browser_diagnostics is not None
    assert runner.browser_diagnostics.identity.user_id == "user-cookie"
    assert runner.browser_diagnostics.identity.conversation_id == "conv-cookie"
    assert runner.browser_diagnostics.identity.extraction_source == "cookies"


@pytest.mark.asyncio
async def test_refresh_identity_context_falls_back_to_auth_session() -> None:
    runner = _make_runner()
    runner.browser_driver = FakeBrowserDriver(
        page=FakePage({}, raise_on_evaluate=True),
        context=FakeContext(
            [],
            FakeResponse(
                200,
                {
                    "session": {"user_id": "user-session"},
                    "conversation_id": "conv-session",
                },
            ),
        ),
    )

    await runner._refresh_identity_context()

    assert runner.browser_diagnostics is not None
    assert runner.browser_diagnostics.identity.user_id == "user-session"
    assert runner.browser_diagnostics.identity.conversation_id == "conv-session"
    assert runner.browser_diagnostics.identity.extraction_source == "auth_session"
    assert runner.browser_diagnostics.identity.auth_session_url == "https://app.example.test/auth/session"
