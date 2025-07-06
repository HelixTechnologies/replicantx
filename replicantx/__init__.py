# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
ReplicantX - End-to-end testing harness for AI agents via web service APIs.

This package provides tools for testing AI agents by calling their HTTP APIs
with configurable authentication, assertions, and reporting.
"""

__version__ = "0.1.0"
__author__ = "ReplicantX Team"
__email__ = "team@replicantx.ai"

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
] 