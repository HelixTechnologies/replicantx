# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
ReplicantX - End-to-end testing harness for AI agents via web service APIs.

This package provides tools for testing AI agents by calling their HTTP APIs
with configurable authentication, assertions, and reporting.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("replicantx")
except PackageNotFoundError:
    __version__ = "0.0.0"
__author__ = "Helix Technologies Limited"
__email__ = "team@replicantx.org"

from .models import (
    Message,
    Step,
    StepResult,
    ScenarioConfig,
    ScenarioReport,
    AuthConfig,
    AssertionResult,
    TestSuiteReport,
    AuthProvider,
    TestLevel,
    AssertionType,
    ReplicantConfig,
    LLMConfig,
    # Browser mode exports
    InteractionMode,
    GoalEvidenceMode,
    TraceMode,
    PageSettleStrategy,
    BrowserConfig,
    BrowserObservation,
    BrowserAction,
    BrowserActionResult,
    InteractiveElement,
    ViewportConfig,
    GoalEvaluationResult,
    BrowserNetworkEvent,
    BrowserConsoleEvent,
    BrowserPageErrorEvent,
    BrowserWebSocketEvent,
    BrowserIdentityContext,
    BrowserTurnDiagnostic,
    BrowserScenarioDiagnostics,
    PayloadFormat,
    SessionMode,
    SessionFormat,
    SessionPlacement,
    GoalEvaluationMode,
    IssueMode,
    IssueArtifactUploadMode,
    IssueDecision,
    LogfireRecord,
    LogfireExcerpt,
    IssueArtifactLink,
    IssueClassification,
    IssueBundle,
)

__all__ = [
    "__version__",
    "Message",
    "Step",
    "StepResult",
    "ScenarioConfig",
    "ScenarioReport",
    "AuthConfig",
    "AssertionResult",
    "TestSuiteReport",
    "AuthProvider",
    "TestLevel",
    "AssertionType",
    "ReplicantConfig",
    "LLMConfig",
    # Browser mode
    "InteractionMode",
    "GoalEvidenceMode",
    "TraceMode",
    "PageSettleStrategy",
    "BrowserConfig",
    "BrowserObservation",
    "BrowserAction",
    "BrowserActionResult",
    "InteractiveElement",
    "ViewportConfig",
    "GoalEvaluationResult",
    "BrowserNetworkEvent",
    "BrowserConsoleEvent",
    "BrowserPageErrorEvent",
    "BrowserWebSocketEvent",
    "BrowserIdentityContext",
    "BrowserTurnDiagnostic",
    "BrowserScenarioDiagnostics",
    "PayloadFormat",
    "SessionMode",
    "SessionFormat",
    "SessionPlacement",
    "GoalEvaluationMode",
    "IssueMode",
    "IssueArtifactUploadMode",
    "IssueDecision",
    "LogfireRecord",
    "LogfireExcerpt",
    "IssueArtifactLink",
    "IssueClassification",
    "IssueBundle",
]
