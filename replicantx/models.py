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

    # Evidence for goal evaluation
    goal_evidence: GoalEvidenceMode = Field(GoalEvidenceMode.DOM, description="Evidence type for goal evaluation")
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
    error: Optional[str] = Field(None, description="Overall error message if scenario failed")
    conversation_history: Optional[str] = Field(None, description="Complete conversation history for agent scenarios")
    justification: Optional[str] = Field(None, description="Explanation of why the scenario passed or failed")
    goal_evaluation_result: Optional[GoalEvaluationResult] = Field(None, description="Goal evaluation result for agent scenarios")
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