# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).

"""
Pydantic v2 models for ReplicantX testing harness.

This module defines all the data structures used throughout the application
including test scenarios, messages, steps, authentication, and reports.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, model_validator


class AuthProvider(str, Enum):
    """Supported authentication providers."""
    SUPABASE = "supabase"
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
    llm: LLMConfig = Field(default_factory=LLMConfig, description="LLM configuration for response generation")


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