# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Data models for ReplicantX test scenarios and results.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthProvider(str, Enum):
    """Supported authentication providers."""
    SUPABASE = "supabase"
    SUPABASE_MAGIC_LINK = "supabase_magic_link"
    JWT = "jwt"
    NOOP = "noop"


class TestLevel(str, Enum):
    """Test scenario levels."""
    BASIC = "basic"
    AGENT = "agent"


class AssertionType(str, Enum):
    """Types of assertions that can be made."""
    CONTAINS = "contains"
    REGEX = "regex"
    EQUALS = "equals"
    NOT_CONTAINS = "not_contains"


class PayloadFormat(str, Enum):
    """Supported API payload formats."""
    OPENAI = "openai"  # OpenAI chat completion format
    SIMPLE = "simple"  # Simple message-only format
    ANTHROPIC = "anthropic"  # Anthropic Claude format
    LEGACY = "legacy"  # Current ReplicantX format (backward compatibility)
    # Session-aware formats
    OPENAI_SESSION = "openai_session"  # OpenAI format with session ID
    SIMPLE_SESSION = "simple_session"  # Simple format with session ID
    RESTFUL_SESSION = "restful_session"  # RESTful resource format


class SessionMode(str, Enum):
    """Session management modes."""
    DISABLED = "disabled"  # No session management (legacy behavior)
    AUTO = "auto"  # Auto-generate session ID
    FIXED = "fixed"  # Use fixed session ID from config
    ENV = "env"  # Use session ID from environment variable


class SessionFormat(str, Enum):
    """Session ID generation formats."""
    REPLICANTX = "replicantx"  # replicantx_xxxxxxxx format
    UUID = "uuid"  # Standard UUID format


class SessionPlacement(str, Enum):
    """Where to place the session ID."""
    HEADER = "header"  # In HTTP headers
    BODY = "body"  # In request body/payload
    URL = "url"  # In URL path (RESTful)


class GoalEvaluationMode(str, Enum):
    """Goal evaluation modes."""
    KEYWORDS = "keywords"  # Simple keyword matching (legacy behavior)
    INTELLIGENT = "intelligent"  # LLM-based goal evaluation
    HYBRID = "hybrid"  # LLM with keyword fallback


class InteractionMode(str, Enum):
    """Interaction mode for agent scenarios."""
    API = "api"  # HTTP API mode (default)
    BROWSER = "browser"  # Browser automation mode with Playwright


class GoalEvidenceMode(str, Enum):
    """Evidence types for goal evaluation in browser mode."""
    DOM = "dom"  # DOM-based evidence (default)
    SCREENSHOT = "screenshot"  # Screenshot-based evidence
    DOM_THEN_SCREENSHOT = "dom_then_screenshot"  # Try DOM first, fallback to screenshot
    BOTH = "both"  # Always use both DOM and screenshot


class TraceMode(str, Enum):
    """Playwright trace recording mode."""
    OFF = "off"  # No tracing
    RETAIN_ON_FAILURE = "retain-on-failure"  # Keep trace only on failure
    ON = "on"  # Always keep trace


class IssueMode(str, Enum):
    """How ReplicantX should handle issue processing."""
    OFF = "off"
    AUTO_HIGH_CONFIDENCE = "auto-high-confidence"
    DRAFT_ONLY = "draft-only"


class IssueArtifactUploadMode(str, Enum):
    """Whether issue artifacts should be uploaded."""
    OFF = "off"
    ON = "on"


class IssueDecision(str, Enum):
    """Classifier output for a browser issue candidate."""
    AUTO_FILE = "auto_file"
    REVIEW = "review"
    SKIP = "skip"


class LLMConfig(BaseModel):
    """Configuration for LLM using PydanticAI models."""
    model_config = ConfigDict(extra="forbid")
    
    model: str = Field("test", description="PydanticAI model name (e.g., 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet-latest', 'test')")
    temperature: Optional[float] = Field(None, description="Temperature for response generation")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens for response")
    
    @model_validator(mode='after')
    def validate_llm_config(self) -> 'LLMConfig':
        """Validate LLM configuration."""
        # PydanticAI handles model validation internally
        return self


class Message(BaseModel):
    """A message exchanged between user and AI agent."""
    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="Role of the message sender (user/assistant)")
    content: str = Field(..., description="Content of the message")
    timestamp: datetime = Field(default_factory=datetime.now, description="When message was sent")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# Browser mode models

class InteractiveElement(BaseModel):
    """An interactive element on a web page."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable element ID for the current turn")
    role: str = Field(..., description="Element role (button, link, textbox, menuitem, etc.)")
    name: str = Field(..., description="Best-effort accessible name or inner text")
    tag_name: str = Field("", description="HTML tag name (e.g., INPUT, BUTTON, A)")
    placeholder: Optional[str] = Field(None, description="Placeholder text if present")
    current_value: Optional[str] = Field(None, description="Current visible value if readable")
    is_typeahead: bool = Field(
        False,
        description="Whether the control appears to behave like a combobox/type-ahead",
    )
    is_expanded: Optional[bool] = Field(
        None,
        description="Whether the control is currently expanded",
    )
    is_required: bool = Field(
        False,
        description="Whether the field is marked as required (required attribute, aria-required, or a * label indicator)",
    )
    locator: Optional[str] = Field(None, description="Playwright locator strategy (internal use)")


class BrowserObservation(BaseModel):
    """A compact, LLM-friendly snapshot of a web page."""
    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="Current page URL")
    title: str = Field(..., description="Page title")
    visible_text: str = Field(..., description="Sanitized and truncated visible text")
    interactive_elements: List[InteractiveElement] = Field(
        default_factory=list,
        description="List of interactive elements (capped)"
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="When observation was captured")


class ViewportConfig(BaseModel):
    """Browser viewport configuration."""
    model_config = ConfigDict(extra="forbid")

    width: int = Field(1400, description="Viewport width in pixels")
    height: int = Field(900, description="Viewport height in pixels")


class BrowserConfig(BaseModel):
    """Configuration for browser mode automation."""
    model_config = ConfigDict(extra="forbid")

    start_url: str = Field(..., description="Initial URL to navigate to")
    headless: bool = Field(True, description="Whether to run browser in headless mode")
    browser_type: str = Field("chromium", description="Browser type: chromium, firefox, or webkit")
    viewport: ViewportConfig = Field(default_factory=ViewportConfig, description="Browser viewport dimensions")
    navigation_timeout_seconds: int = Field(30, description="Timeout for page navigation")
    action_timeout_seconds: int = Field(15, description="Timeout for individual actions")

    # Observation controls
    max_interactive_elements: int = Field(40, description="Maximum interactive elements to extract")
    max_visible_text_chars: int = Field(6000, description="Maximum visible text characters to extract")

    # Planner model (decides what action to take each turn)
    planner_model: Optional[str] = Field(
        None,
        description="PydanticAI model for the browser planner agent (e.g., 'openai:gpt-5.2'). Uses screenshot + DOM to decide actions. Falls back to main LLM model if not specified."
    )

    # Evidence for goal evaluation
    goal_evidence: GoalEvidenceMode = Field(GoalEvidenceMode.DOM, description="Evidence type for goal evaluation")
    screenshot_evaluation_model: Optional[str] = Field(
        None,
        description="PydanticAI model for screenshot-based goal evaluation (e.g., 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet-latest'). If not specified, uses goal_evaluation_model or main LLM model."
    )
    screenshot_on_each_turn: bool = Field(False, description="Whether to capture screenshot each turn")
    screenshot_on_failure: bool = Field(True, description="Whether to capture screenshot on failure")

    # Safety
    domain_allowlist: List[str] = Field(
        default_factory=list,
        description="Allowed domains for navigation (empty = no restriction)"
    )

    # Artifacts
    trace: TraceMode = Field(TraceMode.RETAIN_ON_FAILURE, description="Playwright trace recording mode")


class BrowserAction(BaseModel):
    """An action to perform in the browser."""
    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(..., description="Type of action: send_chat, click, fill, press, wait, scroll, navigate")
    target: Optional[str] = Field(None, description="Target element ID (for click, fill)")
    value: Optional[str] = Field(None, description="Value to set (for fill, send_chat)")
    direction: Optional[str] = Field(None, description="Direction for scroll: up or down")
    amount: Optional[int] = Field(None, description="Amount to scroll in pixels")
    duration_ms: Optional[int] = Field(None, description="Wait duration in milliseconds")
    url: Optional[str] = Field(None, description="URL to navigate to")


class BrowserActionResult(BaseModel):
    """Result of executing a browser action."""
    model_config = ConfigDict(extra="forbid")

    action: BrowserAction = Field(..., description="The action that was executed")
    success: bool = Field(..., description="Whether the action succeeded")
    message: str = Field(..., description="Human-readable result message")
    observation: Optional[BrowserObservation] = Field(None, description="Page observation after action")
    screenshot_path: Optional[str] = Field(None, description="Path to screenshot if captured")
    error: Optional[str] = Field(None, description="Error message if action failed")
    latency_ms: float = Field(..., description="Action execution time in milliseconds")


class BrowserNetworkEvent(BaseModel):
    """Normalized Playwright network event for diagnostics."""
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., description="response or requestfailed")
    url: str = Field(..., description="Request URL")
    method: str = Field(..., description="HTTP method")
    resource_type: Optional[str] = Field(None, description="Playwright resource type")
    status_code: Optional[int] = Field(None, description="HTTP response status code")
    failure_text: Optional[str] = Field(None, description="Request failure text")
    is_first_party: bool = Field(False, description="Whether the URL belongs to the app under test")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the event was observed")


class BrowserConsoleEvent(BaseModel):
    """Normalized browser console event."""
    model_config = ConfigDict(extra="forbid")

    level: str = Field(..., description="Console severity level")
    text: str = Field(..., description="Console message text")
    source_url: Optional[str] = Field(None, description="Originating script URL")
    line_number: Optional[int] = Field(None, description="Source line number")
    column_number: Optional[int] = Field(None, description="Source column number")
    is_first_party: bool = Field(False, description="Whether the source belongs to the app under test")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the event was observed")


class BrowserPageErrorEvent(BaseModel):
    """Unhandled page error surfaced by Playwright."""
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="Page error message")
    stack: Optional[str] = Field(None, description="Stack trace if available")
    is_first_party: bool = Field(True, description="Whether the source belongs to the app under test")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the error was observed")


class BrowserWebSocketEvent(BaseModel):
    """Normalized websocket lifecycle event."""
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(
        ...,
        description="Lifecycle event type: open, framesent, framereceived, or close",
    )
    url: str = Field(..., description="Websocket URL")
    payload_preview: Optional[str] = Field(
        None,
        description="Optional preview of a websocket payload",
    )
    payload_size: Optional[int] = Field(
        None,
        description="Best-effort payload size in bytes or characters",
    )
    is_first_party: bool = Field(
        False,
        description="Whether the websocket belongs to the app under test",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the websocket event was observed",
    )


class BrowserIdentityContext(BaseModel):
    """Correlation identifiers extracted from the browser session."""
    model_config = ConfigDict(extra="forbid")

    user_id: Optional[str] = Field(None, description="Authenticated user ID")
    conversation_id: Optional[str] = Field(None, description="Conversation/session ID")
    extraction_source: str = Field(
        "unavailable",
        description="How the correlation identifiers were extracted",
    )
    auth_session_url: Optional[str] = Field(
        None,
        description="Auth session endpoint used for fallback extraction",
    )


class BrowserTurnDiagnostic(BaseModel):
    """Per-turn diagnostics for browser scenarios."""
    model_config = ConfigDict(extra="forbid")

    turn_index: int = Field(..., description="Turn index in the browser loop")
    planned_reasoning: str = Field("", description="Planner reasoning for the action")
    planned_action: Optional[BrowserAction] = Field(
        None,
        description="Browser action chosen for this turn",
    )
    page_url_before: Optional[str] = Field(None, description="URL before the action")
    page_title_before: Optional[str] = Field(None, description="Page title before the action")
    page_url_after: Optional[str] = Field(None, description="URL after the action")
    page_title_after: Optional[str] = Field(None, description="Page title after the action")
    action_success: bool = Field(..., description="Whether the action succeeded")
    action_message: str = Field(..., description="Human-readable action outcome")
    error: Optional[str] = Field(None, description="Action or turn error")
    screenshot_paths: List[str] = Field(
        default_factory=list,
        description="Screenshots captured for this turn",
    )
    network_event_indexes: List[int] = Field(
        default_factory=list,
        description="Indexes into BrowserScenarioDiagnostics.network_events for this turn",
    )
    console_event_indexes: List[int] = Field(
        default_factory=list,
        description="Indexes into BrowserScenarioDiagnostics.console_events for this turn",
    )
    page_error_indexes: List[int] = Field(
        default_factory=list,
        description="Indexes into BrowserScenarioDiagnostics.page_errors for this turn",
    )
    websocket_event_indexes: List[int] = Field(
        default_factory=list,
        description="Indexes into BrowserScenarioDiagnostics.websocket_events for this turn",
    )
    observation_excerpt: str = Field(
        "",
        description="Compact excerpt of the post-action observation",
    )


class BrowserScenarioDiagnostics(BaseModel):
    """Structured diagnostics captured during browser execution."""
    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(..., description="Scenario name")
    goal: str = Field(..., description="Replicant goal")
    start_url: str = Field(..., description="Scenario start URL")
    started_at: datetime = Field(..., description="When browser execution started")
    completed_at: Optional[datetime] = Field(None, description="When browser execution completed")
    environment: Optional[str] = Field(None, description="Execution environment label")
    artifact_dir: Optional[str] = Field(None, description="Artifact directory for the scenario")
    trace_path: Optional[str] = Field(None, description="Trace path if captured")
    identity: BrowserIdentityContext = Field(
        default_factory=BrowserIdentityContext,
        description="Correlation identifiers for this run",
    )
    turns: List[BrowserTurnDiagnostic] = Field(
        default_factory=list,
        description="Per-turn diagnostics",
    )
    network_events: List[BrowserNetworkEvent] = Field(
        default_factory=list,
        description="Normalized network events",
    )
    console_events: List[BrowserConsoleEvent] = Field(
        default_factory=list,
        description="Browser console events",
    )
    page_errors: List[BrowserPageErrorEvent] = Field(
        default_factory=list,
        description="Unhandled page errors",
    )
    websocket_events: List[BrowserWebSocketEvent] = Field(
        default_factory=list,
        description="Observed websocket activity",
    )


class LogfireRecord(BaseModel):
    """A compact Logfire record excerpt."""
    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(..., description="Record timestamp")
    level: Optional[str] = Field(None, description="Log level")
    message: Optional[str] = Field(None, description="Human-readable message")
    span_name: Optional[str] = Field(None, description="Logfire span name")
    trace_id: Optional[str] = Field(None, description="Trace ID")
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured attributes associated with the record",
    )


class LogfireExcerpt(BaseModel):
    """Query metadata and compact results from Logfire."""
    model_config = ConfigDict(extra="forbid")

    query_window_start: Optional[str] = Field(None, description="Start of the query window")
    query_window_end: Optional[str] = Field(None, description="End of the query window")
    query_sql: Optional[str] = Field(None, description="Rendered SQL used for the query")
    fetched: bool = Field(False, description="Whether the query succeeded")
    unavailable_reason: Optional[str] = Field(None, description="Why logs are unavailable")
    records: List[LogfireRecord] = Field(
        default_factory=list,
        description="Compact Logfire records",
    )


class IssueArtifactLink(BaseModel):
    """Artifact metadata for issue generation."""
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., description="Artifact type such as screenshot or trace")
    label: str = Field(..., description="Human-readable artifact label")
    local_path: str = Field(..., description="Local filesystem path")
    uploaded_url: Optional[str] = Field(None, description="Uploaded or signed URL")


class IssueClassification(BaseModel):
    """Classifier output for a browser issue candidate."""
    model_config = ConfigDict(extra="forbid")

    decision: IssueDecision = Field(..., description="Classifier decision")
    confidence: float = Field(..., description="Classifier confidence from 0 to 1")
    subtypes: List[str] = Field(
        default_factory=list,
        description="Normalized subtype labels",
    )
    fingerprint: str = Field(..., description="Deterministic issue fingerprint")
    summary: str = Field(..., description="Short issue summary")
    reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable rationale for the decision",
    )
    relevant_turn_indexes: List[int] = Field(
        default_factory=list,
        description="Turn indexes relevant to the issue summary",
    )


class IssueBundle(BaseModel):
    """Standalone issue bundle written to disk for browser scenarios."""
    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(..., description="Scenario name")
    scenario_file: Optional[str] = Field(None, description="Source YAML path")
    repo_target: str = Field(..., description="Repository to file against")
    goal: str = Field(..., description="Replicant goal")
    environment: Optional[str] = Field(None, description="Execution environment label")
    generated_at: datetime = Field(default_factory=datetime.now, description="When the bundle was generated")
    scenario_passed: bool = Field(..., description="Whether the scenario passed")
    scenario_error: Optional[str] = Field(None, description="Top-level scenario error")
    classification: IssueClassification = Field(..., description="Classifier output")
    diagnostics: BrowserScenarioDiagnostics = Field(..., description="Browser diagnostics for the scenario")
    artifact_links: List[IssueArtifactLink] = Field(
        default_factory=list,
        description="Artifacts referenced by the issue bundle",
    )
    logfire_excerpt: Optional[LogfireExcerpt] = Field(
        None,
        description="Server-side log excerpt if fetched",
    )
    issue_title: str = Field(..., description="Rendered issue title")
    issue_body: str = Field(..., description="Rendered issue body markdown")


class GoalEvaluationResult(BaseModel):
    """Result of goal evaluation."""
    model_config = ConfigDict(extra="forbid")
    
    goal_achieved: bool = Field(..., description="Whether the goal has been achieved")
    confidence: float = Field(..., description="Confidence score from 0.0 to 1.0")
    reasoning: str = Field(..., description="Explanation of why the goal is/isn't achieved")
    evaluation_method: str = Field(..., description="Method used: 'keywords', 'intelligent', or 'hybrid'")
    fallback_used: bool = Field(False, description="Whether hybrid mode fell back to keywords")
    timestamp: datetime = Field(default_factory=datetime.now, description="When evaluation was performed")


class AssertionResult(BaseModel):
    """Result of an assertion check."""
    model_config = ConfigDict(extra="forbid")
    
    assertion_type: AssertionType = Field(..., description="Type of assertion")
    expected: Union[str, List[str]] = Field(..., description="Expected value(s)")
    actual: str = Field(..., description="Actual response content")
    passed: bool = Field(..., description="Whether assertion passed")
    error_message: Optional[str] = Field(None, description="Error message if assertion failed")


class StepResult(BaseModel):
    """Result of executing a test step."""
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(..., description="Index of the step in the scenario")
    user_message: str = Field(..., description="User message sent")
    response: str = Field(..., description="AI agent response")
    latency_ms: float = Field(..., description="Response latency in milliseconds")
    assertions: List[AssertionResult] = Field(default_factory=list, description="Assertion results")
    passed: bool = Field(..., description="Whether all assertions passed")
    error: Optional[str] = Field(None, description="Error message if step failed")
    timestamp: datetime = Field(default_factory=datetime.now, description="When step was executed")

    # Browser mode specific fields (optional)
    action_type: Optional[str] = Field(None, description="Action type in browser mode (e.g., click, send_chat)")
    action_summary: Optional[str] = Field(None, description="Summary of browser action performed")
    planner_reasoning: Optional[str] = Field(None, description="Planner reasoning for the chosen browser action")
    page_url: Optional[str] = Field(None, description="Current page URL in browser mode")
    observation_excerpt: Optional[str] = Field(None, description="Excerpt from page observation")
    artifact_paths: Dict[str, str] = Field(
        default_factory=dict,
        description="Paths to artifacts (screenshot, trace, etc.)"
    )


class Step(BaseModel):
    """A single test step in a scenario."""
    model_config = ConfigDict(extra="forbid")
    
    user: str = Field(..., description="User message to send")
    expect_contains: Optional[List[str]] = Field(None, description="Text that must be contained in response")
    expect_regex: Optional[str] = Field(None, description="Regex pattern that must match response")
    expect_equals: Optional[str] = Field(None, description="Exact text that response must equal")
    expect_not_contains: Optional[List[str]] = Field(None, description="Text that must NOT be in response")
    timeout_seconds: Optional[int] = Field(30, description="Timeout for this step in seconds")
    
    @model_validator(mode='after')
    def validate_expectations(self) -> 'Step':
        """Validate that at least one expectation is provided."""
        expectations = [
            self.expect_contains,
            self.expect_regex, 
            self.expect_equals,
            self.expect_not_contains
        ]
        if not any(exp is not None for exp in expectations):
            raise ValueError("At least one expectation must be provided")
        return self


class AuthConfig(BaseModel):
    """Authentication configuration."""
    model_config = ConfigDict(extra="forbid")

    provider: AuthProvider = Field(..., description="Authentication provider")
    # Supabase auth fields
    email: Optional[str] = Field(None, description="Email for Supabase auth")
    password: Optional[str] = Field(None, description="Password for Supabase auth")
    project_url: Optional[str] = Field(None, description="Supabase project URL")
    api_key: Optional[str] = Field(None, description="Supabase API key")
    # Supabase magic link auth fields
    service_role_key: Optional[str] = Field(None, description="Service role key for Supabase magic link auth")
    user_mode: Optional[str] = Field(None, description="User mode for magic link: 'generated' or 'fixed'")
    redirect_to: Optional[str] = Field(None, description="Redirect URL for magic link")
    app_refresh_endpoint: Optional[str] = Field(None, description="App refresh endpoint for cookie setting")
    # JWT auth fields
    token: Optional[str] = Field(None, description="JWT token for authentication")
    # Additional headers for custom auth
    headers: Dict[str, str] = Field(default_factory=dict, description="Additional auth headers")

    @model_validator(mode='after')
    def validate_auth_config(self) -> 'AuthConfig':
        """Validate authentication configuration based on provider."""
        if self.provider == AuthProvider.SUPABASE:
            required_fields = ['email', 'password', 'project_url', 'api_key']
            missing = [field for field in required_fields if getattr(self, field) is None]
            if missing:
                raise ValueError(f"Supabase auth requires: {missing}")
        elif self.provider == AuthProvider.SUPABASE_MAGIC_LINK:
            required_fields = ['project_url', 'service_role_key', 'app_refresh_endpoint']
            missing = [field for field in required_fields if getattr(self, field) is None]
            if missing:
                raise ValueError(f"Supabase magic link auth requires: {missing}")
            if self.user_mode == 'fixed' and not self.email:
                raise ValueError("Supabase magic link auth with user_mode='fixed' requires email")
        elif self.provider == AuthProvider.JWT:
            if self.token is None:
                raise ValueError("JWT auth requires token")
        return self


class ReplicantConfig(BaseModel):
    """Configuration for the Replicant agent in agent-level scenarios."""
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., description="The goal the Replicant should achieve")
    facts: Dict[str, Any] = Field(default_factory=dict, description="Facts the Replicant knows (e.g., name, email, preferences)")
    system_prompt: str = Field(
        "You are a helpful user trying to achieve a goal. You have access to certain facts but may not remember to provide all details upfront. Answer questions based on your available facts.",
        description="System prompt for the Replicant agent"
    )
    initial_message: str = Field(..., description="Initial message to start the conversation")
    max_turns: int = Field(20, description="Maximum conversation turns")
    completion_keywords: List[str] = Field(
        default_factory=lambda: ["complete", "finished", "done", "confirmed", "thank you", "success"],
        description="Keywords that indicate conversation completion"
    )

    # Interaction mode
    interaction_mode: InteractionMode = Field(InteractionMode.API, description="Interaction mode: 'api' (default) or 'browser'")

    # API mode configuration (legacy)
    fullconversation: bool = Field(True, description="Whether to send full conversation history (including responses) with each request (API mode only)")
    payload_format: PayloadFormat = Field(PayloadFormat.OPENAI, description="API payload format: 'openai', 'simple', 'anthropic', 'legacy', or session-aware formats (API mode only)")

    # Session management configuration (API mode only)
    session_mode: SessionMode = Field(SessionMode.DISABLED, description="Session management mode: 'disabled', 'auto', 'fixed', or 'env' (API mode only)")
    session_id: Optional[str] = Field(None, description="Fixed session ID (used when session_mode is 'fixed')")
    session_timeout: int = Field(300, description="Session timeout in seconds (default: 5 minutes)")
    session_format: SessionFormat = Field(SessionFormat.UUID, description="Session ID format: 'replicantx' or 'uuid' (default: uuid)")
    session_placement: SessionPlacement = Field(SessionPlacement.BODY, description="Session ID placement: 'header', 'body', or 'url' (default: body)")
    session_variable_name: str = Field("session_id", description="Name of the session variable in header/body (default: session_id)")

    # LLM configuration
    llm: LLMConfig = Field(default_factory=LLMConfig, description="LLM configuration for response generation")

    # Goal evaluation configuration
    goal_evaluation_mode: GoalEvaluationMode = Field(GoalEvaluationMode.KEYWORDS, description="Goal evaluation mode: 'keywords' (default), 'intelligent', or 'hybrid'")
    goal_evaluation_model: Optional[str] = Field(None, description="PydanticAI model for goal evaluation (defaults to main LLM model if not specified)")
    goal_evaluation_prompt: Optional[str] = Field(None, description="Custom prompt for goal evaluation (uses default if not specified)")

    # Browser mode configuration
    browser: Optional[BrowserConfig] = Field(None, description="Browser automation configuration (browser mode only)")


class ScenarioConfig(BaseModel):
    """Configuration for a test scenario."""
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Human-readable name of the scenario")
    base_url: str = Field(..., description="Base URL for the API endpoint")
    auth: AuthConfig = Field(..., description="Authentication configuration")
    level: TestLevel = Field(..., description="Test level (basic or agent)")
    # For basic scenarios
    steps: Optional[List[Step]] = Field(None, description="List of test steps to execute (basic level only)")
    # For agent scenarios
    replicant: Optional[ReplicantConfig] = Field(None, description="Replicant agent configuration (agent level only)")
    timeout_seconds: int = Field(120, description="Overall timeout for scenario")
    max_retries: int = Field(3, description="Maximum number of retries per step")
    retry_delay_seconds: float = Field(1.0, description="Delay between retries")
    validate_politeness: bool = Field(False, description="Whether to validate politeness/conversational tone in responses")
    parallel: bool = Field(False, description="Whether to run this scenario in parallel with others")
    
    @model_validator(mode='after')
    def validate_scenario(self) -> 'ScenarioConfig':
        """Validate scenario configuration."""
        if self.level == TestLevel.BASIC:
            if not self.steps:
                raise ValueError("Basic scenarios must have at least one step")
        elif self.level == TestLevel.AGENT:
            if not self.replicant:
                raise ValueError("Agent scenarios must have replicant configuration")
        return self


class ScenarioReport(BaseModel):
    """Report for a completed test scenario."""
    model_config = ConfigDict(extra="forbid")
    
    scenario_name: str = Field(..., description="Name of the scenario")
    passed: bool = Field(..., description="Whether scenario passed overall")
    total_steps: int = Field(..., description="Total number of steps")
    passed_steps: int = Field(..., description="Number of steps that passed")
    failed_steps: int = Field(..., description="Number of steps that failed")
    total_duration_ms: float = Field(..., description="Total execution time in milliseconds")
    step_results: List[StepResult] = Field(default_factory=list, description="Results for each step")
    source_file: Optional[str] = Field(None, description="Scenario YAML file path")
    error: Optional[str] = Field(None, description="Overall error message if scenario failed")
    conversation_history: Optional[str] = Field(None, description="Complete conversation history for agent scenarios")
    justification: Optional[str] = Field(None, description="Explanation of why the scenario passed or failed")
    goal_evaluation_result: Optional[GoalEvaluationResult] = Field(None, description="Goal evaluation result for agent scenarios")
    artifact_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Artifact summary for the scenario",
    )
    browser_diagnostics: Optional[BrowserScenarioDiagnostics] = Field(
        None,
        description="Structured browser diagnostics for browser scenarios",
    )
    issue_classification: Optional[IssueClassification] = Field(
        None,
        description="Issue classifier output if issue processing was run",
    )
    issue_bundle_path: Optional[str] = Field(
        None,
        description="Path to the issue bundle on disk",
    )
    issue_markdown_path: Optional[str] = Field(
        None,
        description="Path to the rendered issue markdown draft",
    )
    issue_url: Optional[str] = Field(
        None,
        description="Created or updated issue URL",
    )
    started_at: datetime = Field(default_factory=datetime.now, description="When scenario started")
    completed_at: Optional[datetime] = Field(None, description="When scenario completed")
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.passed_steps / self.total_steps) * 100
    
    @property
    def duration_seconds(self) -> float:
        """Total duration in seconds."""
        return self.total_duration_ms / 1000.0


class TestSuiteReport(BaseModel):
    """Report for a complete test suite run."""
    model_config = ConfigDict(extra="forbid")
    
    total_scenarios: int = Field(..., description="Total number of scenarios")
    passed_scenarios: int = Field(..., description="Number of scenarios that passed")
    failed_scenarios: int = Field(..., description="Number of scenarios that failed")
    scenario_reports: List[ScenarioReport] = Field(default_factory=list, description="Individual scenario reports")
    started_at: datetime = Field(default_factory=datetime.now, description="When test suite started")
    completed_at: Optional[datetime] = Field(None, description="When test suite completed")
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_scenarios == 0:
            return 0.0
        return (self.passed_scenarios / self.total_scenarios) * 100
    
    @property
    def total_duration_ms(self) -> float:
        """Total duration of all scenarios in milliseconds."""
        return sum(report.total_duration_ms for report in self.scenario_reports)
    
    @property
    def duration_seconds(self) -> float:
        """Total duration in seconds."""
        return self.total_duration_ms / 1000.0 
