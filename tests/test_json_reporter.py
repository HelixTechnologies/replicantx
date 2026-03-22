from datetime import datetime, timezone

from replicantx.models import (
    BrowserIdentityContext,
    BrowserScenarioDiagnostics,
    IssueClassification,
    IssueDecision,
    ScenarioReport,
    StepResult,
)
from replicantx.reporters import JSONReporter


def test_json_reporter_serializes_issue_fields() -> None:
    started_at = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    diagnostics = BrowserScenarioDiagnostics(
        scenario_name="Checkout failure",
        goal="Book a trip",
        start_url="https://app.example.test/start",
        started_at=started_at,
        identity=BrowserIdentityContext(
            user_id="user-123",
            conversation_id="conv-123",
            extraction_source="local_storage",
        ),
    )
    report = ScenarioReport(
        scenario_name="Checkout failure",
        passed=False,
        total_steps=1,
        passed_steps=0,
        failed_steps=1,
        total_duration_ms=1234.0,
        step_results=[
            StepResult(
                step_index=0,
                user_message="Submit checkout form",
                response="Checkout failed",
                latency_ms=123.0,
                passed=False,
                error="Server error",
                planner_reasoning="Submitting the checkout form should complete the booking.",
                action_type="click",
                action_summary="Clicked submit",
                page_url="https://app.example.test/checkout",
                observation_excerpt="Internal server error",
                artifact_paths={"issue_screenshot": "artifacts/failure.png"},
            )
        ],
        source_file="tests/browser_issue.yaml",
        error="Scenario failed",
        browser_diagnostics=diagnostics,
        issue_classification=IssueClassification(
            decision=IssueDecision.AUTO_FILE,
            confidence=0.98,
            subtypes=["network-5xx"],
            fingerprint="abc123",
            summary="Auto file for scenario",
            reasons=["First-party 500 response detected."],
            relevant_turn_indexes=[0],
        ),
        issue_bundle_path="artifacts/issues/checkout/issue_bundle.json",
        issue_markdown_path="artifacts/issues/checkout/issue.md",
        issue_url="https://github.com/HelixTechnologies/helix-agent/issues/42",
        started_at=started_at,
        completed_at=started_at,
    )

    data = JSONReporter()._serialize_scenario_report(report)

    assert data["source_file"] == "tests/browser_issue.yaml"
    assert data["issue_classification"]["decision"] == "auto_file"
    assert data["issue_bundle_path"].endswith("issue_bundle.json")
    assert data["issue_markdown_path"].endswith("issue.md")
    assert data["issue_url"].endswith("/42")
    assert data["browser_diagnostics"]["identity"]["user_id"] == "user-123"
    assert data["step_results"][0]["planner_reasoning"].startswith("Submitting")
    assert data["step_results"][0]["artifact_paths"]["issue_screenshot"] == "artifacts/failure.png"
