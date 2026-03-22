from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from replicantx.issue_reporting import (
    GitHubIssueTracker,
    HttpLogfireClient,
    IssueClassifier,
    IssueProcessingConfig,
    IssueProcessor,
    LogfireQueryConfig,
    SupabaseArtifactUploader,
    _load_logfire_query_config,
)
from replicantx.models import (
    BrowserConsoleEvent,
    BrowserIdentityContext,
    BrowserNetworkEvent,
    BrowserPageErrorEvent,
    BrowserScenarioDiagnostics,
    BrowserTurnDiagnostic,
    IssueArtifactLink,
    IssueArtifactUploadMode,
    IssueDecision,
    IssueMode,
    LogfireExcerpt,
    LogfireRecord,
    ScenarioReport,
    StepResult,
)


def _make_report(
    *,
    name: str = "Browser regression",
    passed: bool = False,
    error: str | None = "Scenario failed",
    observation_excerpt: str = "Checkout page stalled",
    user_id: str | None = "user-123",
    conversation_id: str | None = "conv-123",
    network_events: list[BrowserNetworkEvent] | None = None,
    console_events: list[BrowserConsoleEvent] | None = None,
    page_errors: list[BrowserPageErrorEvent] | None = None,
    turn_error: str | None = "Action failed",
    turn_success: bool = False,
    screenshot_path: str | None = None,
) -> ScenarioReport:
    started_at = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 3, 21, 10, 5, tzinfo=timezone.utc)
    network_events = network_events or []
    console_events = console_events or []
    page_errors = page_errors or []

    turn = BrowserTurnDiagnostic(
        turn_index=0,
        planned_reasoning="Open the checkout form and submit the booking.",
        page_url_before="https://app.example.test/start",
        page_title_before="Start",
        page_url_after="https://app.example.test/checkout",
        page_title_after="Checkout",
        action_success=turn_success,
        action_message="Submit booking form",
        error=turn_error,
        screenshot_paths=[screenshot_path] if screenshot_path else [],
        network_event_indexes=list(range(len(network_events))),
        console_event_indexes=list(range(len(console_events))),
        page_error_indexes=list(range(len(page_errors))),
        observation_excerpt=observation_excerpt,
    )

    diagnostics = BrowserScenarioDiagnostics(
        scenario_name=name,
        goal="Book a trip to Paris",
        start_url="https://app.example.test/start",
        started_at=started_at,
        completed_at=completed_at,
        environment="staging",
        identity=BrowserIdentityContext(
            user_id=user_id,
            conversation_id=conversation_id,
            extraction_source="local_storage" if user_id or conversation_id else "unavailable",
        ),
        turns=[turn],
        network_events=network_events,
        console_events=console_events,
        page_errors=page_errors,
    )

    step_result = StepResult(
        step_index=0,
        user_message="Submit booking form",
        response="Checkout failed",
        latency_ms=321.0,
        passed=turn_success,
        error=turn_error,
        planner_reasoning=turn.planned_reasoning,
        page_url=turn.page_url_after,
        observation_excerpt=observation_excerpt,
        artifact_paths={"issue_screenshot": screenshot_path} if screenshot_path else {},
    )

    return ScenarioReport(
        scenario_name=name,
        passed=passed,
        total_steps=1,
        passed_steps=1 if turn_success else 0,
        failed_steps=0 if turn_success else 1,
        total_duration_ms=300000.0,
        step_results=[step_result],
        source_file="tests/browser_issue.yaml",
        error=error,
        justification="Goal not achieved.",
        browser_diagnostics=diagnostics,
        started_at=started_at,
        completed_at=completed_at,
    )


def _processor_config(tmp_path: Path, *, issue_mode: IssueMode) -> IssueProcessingConfig:
    return IssueProcessingConfig(
        issue_mode=issue_mode,
        issue_repo="HelixTechnologies/helix-agent",
        artifact_upload_mode=IssueArtifactUploadMode.OFF,
        issue_output_dir=tmp_path / "issues",
        artifact_bucket="replicantx-artifacts",
        github_token="github-token",
        logfire_read_token="logfire-token",
        environment="staging",
    )


def test_load_logfire_query_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "replicantx.logfire.yaml"
    config_path.write_text(
        """
service_name: product-api
static_filters:
  - "service_name = {service_name}"
  - "attributes->>'tenant' = 'acme'"
correlation_rules:
  - identity_field: user_id
    expressions:
      - "attributes->>'actor_id' = {value}"
      - "attributes->>'user_id' = {value}"
    combine_with: or
  - identity_field: conversation_id
    expressions:
      - "attributes->>'session_key' = {value}"
time_window:
  before_seconds: 30
  after_seconds: 45
limit: 10
""".strip(),
        encoding="utf-8",
    )

    query_config, resolved_path = _load_logfire_query_config(
        config_path=str(config_path),
        default_service_name="helix-api",
    )

    assert resolved_path == config_path
    assert query_config.service_name == "product-api"
    assert query_config.limit == 10
    assert query_config.time_window.before_seconds == 30
    assert query_config.time_window.after_seconds == 45
    assert query_config.correlation_rules[0].expressions[0] == "attributes->>'actor_id' = {value}"


class StubLogfireClient:
    def __init__(self, excerpt: LogfireExcerpt):
        self.excerpt = excerpt

    async def fetch_excerpt(self, diagnostics: BrowserScenarioDiagnostics) -> LogfireExcerpt:
        return self.excerpt


class StubUploader:
    async def upload_artifacts(
        self,
        *,
        report: ScenarioReport,
        classification,
        local_artifacts,
        allowed_roots,
    ):
        return list(local_artifacts)


class StubIssueTracker:
    def __init__(self, url: str | None = None):
        self.url = url
        self.calls: list[dict[str, object]] = []

    async def create_or_comment(
        self,
        *,
        repo: str,
        title: str,
        body: str,
        fingerprint: str,
        labels,
    ) -> str | None:
        self.calls.append(
            {
                "repo": repo,
                "title": title,
                "body": body,
                "fingerprint": fingerprint,
                "labels": list(labels),
            }
        )
        return self.url


def test_classifier_marks_first_party_500_as_auto_file() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/bookings",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ]
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.AUTO_FILE
    assert "network-5xx" in classification.subtypes
    assert classification.relevant_turn_indexes == [0]


def test_classifier_marks_post_auth_401_as_auto_file() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/me",
                method="GET",
                status_code=401,
                is_first_party=True,
            )
        ]
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.AUTO_FILE
    assert "network-401" in classification.subtypes


def test_classifier_marks_console_error_as_auto_file() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        console_events=[
            BrowserConsoleEvent(
                level="error",
                text="Booking widget crashed",
                source_url="https://app.example.test/assets/app.js",
                is_first_party=True,
            )
        ]
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.AUTO_FILE
    assert "console-error" in classification.subtypes


def test_classifier_keeps_non_blocking_500_when_scenario_passes() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        passed=True,
        error=None,
        turn_success=True,
        turn_error=None,
        observation_excerpt="Booking confirmation displayed",
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/analytics",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ],
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.AUTO_FILE
    assert "network-5xx" in classification.subtypes
    assert any("goal" in reason.lower() and "achieved" in reason.lower() for reason in classification.reasons)
    assert "Goal was still achieved." in classification.summary


def test_classifier_marks_ambiguous_ui_as_review() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        observation_excerpt="Loading spinner still visible after submit",
        turn_error="UI interaction failed after clicking submit",
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.REVIEW
    assert "ambiguous-ui" in classification.subtypes


def test_classifier_marks_playwright_gap_as_skip() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        turn_error="Timeout waiting for selector [data-testid='checkout-submit']",
    )

    classification = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert classification.decision == IssueDecision.SKIP
    assert "playwright-gap" in classification.subtypes


def test_classifier_fingerprint_is_stable() -> None:
    classifier = IssueClassifier()
    report = _make_report(
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/bookings?trace=abc",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ]
    )

    first = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")
    second = classifier.classify(report, repo_target="HelixTechnologies/helix-agent")

    assert first.fingerprint == second.fingerprint


def test_issue_body_renders_with_logfire_records(tmp_path: Path) -> None:
    report = _make_report(
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/bookings",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ],
        screenshot_path=str(tmp_path / "failure.png"),
    )
    processor = IssueProcessor(
        config=_processor_config(tmp_path, issue_mode=IssueMode.DRAFT_ONLY),
        uploader=StubUploader(),
        logfire_client=StubLogfireClient(
            LogfireExcerpt(
                fetched=True,
                records=[
                    LogfireRecord(
                        timestamp="2026-03-21T10:00:10Z",
                        level="error",
                        message="booking failed with 500",
                        span_name="book_trip",
                    )
                ],
            )
        ),
        issue_tracker=StubIssueTracker(),
    )
    classification = processor.classifier.classify(
        report, repo_target="HelixTechnologies/helix-agent"
    )
    body = processor._render_issue_body(
        report=report,
        classification=classification,
        artifact_links=[
            IssueArtifactLink(
                kind="screenshot",
                label="Turn 0 screenshot",
                local_path=str(tmp_path / "failure.png"),
                uploaded_url="https://storage.example.test/failure.png",
            )
        ],
        logfire_excerpt=LogfireExcerpt(
            fetched=True,
            records=[
                LogfireRecord(
                    timestamp="2026-03-21T10:00:10Z",
                    level="error",
                    message="booking failed with 500",
                    span_name="book_trip",
                )
            ],
        ),
    )

    assert "replicantx-fingerprint" in body
    assert "https://storage.example.test/failure.png" in body
    assert "booking failed with 500" in body


def test_issue_body_renders_without_logfire_records(tmp_path: Path) -> None:
    report = _make_report()
    processor = IssueProcessor(
        config=_processor_config(tmp_path, issue_mode=IssueMode.DRAFT_ONLY),
        uploader=StubUploader(),
        logfire_client=StubLogfireClient(
            LogfireExcerpt(fetched=False, unavailable_reason="No identifiers found.")
        ),
        issue_tracker=StubIssueTracker(),
    )
    classification = processor.classifier.classify(
        report, repo_target="HelixTechnologies/helix-agent"
    )
    body = processor._render_issue_body(
        report=report,
        classification=classification,
        artifact_links=[],
        logfire_excerpt=LogfireExcerpt(
            fetched=False,
            unavailable_reason="No identifiers found.",
        ),
    )

    assert "Logs unavailable: No identifiers found." in body


@pytest.mark.asyncio
async def test_process_suite_writes_review_bundle_without_filing(tmp_path: Path) -> None:
    report = _make_report(
        observation_excerpt="Loading spinner still visible after submit",
        turn_error="UI interaction failed after clicking submit",
    )
    tracker = StubIssueTracker(url="https://github.com/HelixTechnologies/helix-agent/issues/10")
    processor = IssueProcessor(
        config=_processor_config(tmp_path, issue_mode=IssueMode.DRAFT_ONLY),
        uploader=StubUploader(),
        logfire_client=StubLogfireClient(
            LogfireExcerpt(fetched=False, unavailable_reason="No matching records found.")
        ),
        issue_tracker=tracker,
    )

    await processor.process_suite([report])

    assert report.issue_classification is not None
    assert report.issue_classification.decision == IssueDecision.REVIEW
    assert report.issue_bundle_path is not None
    assert report.issue_markdown_path is not None
    assert report.issue_url is None
    assert tracker.calls == []
    assert Path(report.issue_bundle_path).is_file()
    assert Path(report.issue_markdown_path).is_file()


@pytest.mark.asyncio
async def test_process_suite_auto_files_high_confidence_issue(tmp_path: Path) -> None:
    screenshot = tmp_path / "failure.png"
    screenshot.write_bytes(b"png")
    report = _make_report(
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/bookings",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ],
        screenshot_path=str(screenshot),
    )
    tracker = StubIssueTracker(url="https://github.com/HelixTechnologies/helix-agent/issues/42")
    processor = IssueProcessor(
        config=_processor_config(tmp_path, issue_mode=IssueMode.AUTO_HIGH_CONFIDENCE),
        uploader=StubUploader(),
        logfire_client=StubLogfireClient(
            LogfireExcerpt(fetched=False, unavailable_reason="No matching records found.")
        ),
        issue_tracker=tracker,
    )

    await processor.process_suite([report])

    assert report.issue_classification is not None
    assert report.issue_classification.decision == IssueDecision.AUTO_FILE
    assert report.issue_url == "https://github.com/HelixTechnologies/helix-agent/issues/42"
    assert len(tracker.calls) == 1
    assert "replicantx-fingerprint" in tracker.calls[0]["body"]


@pytest.mark.asyncio
async def test_process_suite_files_non_blocking_issue_for_passed_scenario(tmp_path: Path) -> None:
    screenshot = tmp_path / "passed-with-error.png"
    screenshot.write_bytes(b"png")
    report = _make_report(
        passed=True,
        error=None,
        turn_success=True,
        turn_error=None,
        observation_excerpt="Booking confirmed successfully",
        network_events=[
            BrowserNetworkEvent(
                event_type="response",
                url="https://app.example.test/api/analytics",
                method="POST",
                status_code=500,
                is_first_party=True,
            )
        ],
        screenshot_path=str(screenshot),
    )
    tracker = StubIssueTracker(url="https://github.com/HelixTechnologies/helix-agent/issues/77")
    processor = IssueProcessor(
        config=_processor_config(tmp_path, issue_mode=IssueMode.AUTO_HIGH_CONFIDENCE),
        uploader=StubUploader(),
        logfire_client=StubLogfireClient(
            LogfireExcerpt(fetched=False, unavailable_reason="No matching records found.")
        ),
        issue_tracker=tracker,
    )

    await processor.process_suite([report])

    assert report.passed is True
    assert report.issue_classification is not None
    assert report.issue_classification.decision == IssueDecision.AUTO_FILE
    assert report.issue_url == "https://github.com/HelixTechnologies/helix-agent/issues/77"
    assert len(tracker.calls) == 1
    assert "Scenario outcome: `passed`" in tracker.calls[0]["body"]


@pytest.mark.asyncio
async def test_supabase_artifact_uploader_returns_signed_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = tmp_path / "failure.png"
    file_path.write_bytes(b"image-bytes")
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.url.path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(
                200,
                json={"signedURL": "/object/sign/replicantx-artifacts/signed/failure.png?token=abc"},
            )
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("replicantx.issue_reporting.httpx.AsyncClient", client_factory)

    uploader = SupabaseArtifactUploader(
        supabase_url="https://supabase.example.test",
        service_role_key="service-role",
        bucket="replicantx-artifacts",
        signed_url_ttl_seconds=3600,
    )
    report = _make_report(screenshot_path=str(file_path))
    classification = IssueClassifier().classify(
        _make_report(
            network_events=[
                BrowserNetworkEvent(
                    event_type="response",
                    url="https://app.example.test/api/bookings",
                    method="POST",
                    status_code=500,
                    is_first_party=True,
                )
            ],
            screenshot_path=str(file_path),
        ),
        repo_target="HelixTechnologies/helix-agent",
    )

    uploaded = await uploader.upload_artifacts(
        report=report,
        classification=classification,
        local_artifacts=[
            IssueArtifactLink(
                kind="screenshot",
                label="Failure screenshot",
                local_path=str(file_path),
            )
        ],
        allowed_roots=[tmp_path],
    )

    assert uploaded[0].uploaded_url == (
        "https://supabase.example.test/storage/v1/object/sign/replicantx-artifacts/"
        "signed/failure.png?token=abc"
    )
    assert requests[0][0] == "POST"
    assert requests[1][0] == "POST"


@pytest.mark.asyncio
async def test_github_tracker_comments_on_existing_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode() if request.content else None
        requests.append((request.method, str(request.url), body))
        if request.url.path == "/search/issues":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "number": 17,
                            "html_url": "https://github.com/HelixTechnologies/helix-agent/issues/17",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/issues/17/comments"):
            return httpx.Response(201, json={"id": 1})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("replicantx.issue_reporting.httpx.AsyncClient", client_factory)

    tracker = GitHubIssueTracker(token="github-token")
    issue_url = await tracker.create_or_comment(
        repo="HelixTechnologies/helix-agent",
        title="ReplicantX bug",
        body="<!-- replicantx-fingerprint: abc123 -->\nissue body",
        fingerprint="abc123",
        labels=["bug", "source:replicantx"],
    )

    assert issue_url == "https://github.com/HelixTechnologies/helix-agent/issues/17"
    assert requests[0][0] == "GET"
    assert requests[1][1].endswith("/issues/17/comments")


@pytest.mark.asyncio
async def test_logfire_client_parses_row_oriented_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = _make_report().browser_diagnostics
    assert diagnostics is not None

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/query"
        return httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "start_timestamp": "2026-03-21T10:01:00Z",
                        "level": "error",
                        "message": "server exploded",
                        "span_name": "book_trip",
                        "trace_id": "trace-123",
                        "attributes": json.dumps({"user_id": "user-123"}),
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("replicantx.issue_reporting.httpx.AsyncClient", client_factory)

    client = HttpLogfireClient(
        read_token="logfire-token",
        base_url="https://logfire.example.test",
        query_config=LogfireQueryConfig.default(service_name="helix-api"),
    )
    excerpt = await client.fetch_excerpt(diagnostics)

    assert excerpt.fetched is True
    assert excerpt.records[0].message == "server exploded"
    assert excerpt.records[0].attributes["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_logfire_client_uses_custom_yaml_query_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = _make_report().browser_diagnostics
    assert diagnostics is not None

    config_path = tmp_path / "replicantx.logfire.yaml"
    config_path.write_text(
        """
service_name: product-api
static_filters:
  - "service_name = {service_name}"
  - "attributes->>'tenant' = 'acme'"
correlation_joiner: and
correlation_rules:
  - identity_field: user_id
    expressions:
      - "attributes->>'actor_id' = {value}"
      - "attributes->>'user_id' = {value}"
    combine_with: or
  - identity_field: conversation_id
    expressions:
      - "attributes->>'session_key' = {value}"
time_window:
  before_seconds: 30
  after_seconds: 45
limit: 10
""".strip(),
        encoding="utf-8",
    )

    query_config, _ = _load_logfire_query_config(
        config_path=str(config_path),
        default_service_name="helix-api",
    )

    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for key, value in request.url.params.multi_items():
            captured_params[key] = value
        return httpx.Response(200, json={"rows": []})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("replicantx.issue_reporting.httpx.AsyncClient", client_factory)

    client = HttpLogfireClient(
        read_token="logfire-token",
        base_url="https://logfire.example.test",
        query_config=query_config,
    )
    excerpt = await client.fetch_excerpt(diagnostics)

    assert excerpt.fetched is True
    assert "service_name = 'product-api'" in excerpt.query_sql
    assert "attributes->>'tenant' = 'acme'" in excerpt.query_sql
    assert "attributes->>'actor_id' = 'user-123'" in excerpt.query_sql
    assert "attributes->>'session_key' = 'conv-123'" in excerpt.query_sql
    assert captured_params["limit"] == "10"
    assert captured_params["row_oriented"] == "true"
    assert captured_params["min_timestamp"].endswith("09:59:30+00:00")
    assert captured_params["max_timestamp"].endswith("10:05:45+00:00")
