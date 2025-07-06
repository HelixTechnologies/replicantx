# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Basic scenario runner for ReplicantX.

This module implements Level 1 (Basic) test scenarios that execute
fixed user messages and validate responses against deterministic assertions.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional

from ..auth import AuthBase, SupabaseAuth, JWTAuth, NoopAuth
from ..models import (
    ScenarioConfig, ScenarioReport, StepResult, AssertionResult,
    AssertionType, AuthProvider, Step
)
from ..tools.http_client import HTTPClient, HTTPResponse
from rich.console import Console


class BasicScenarioRunner:
    """Runner for basic (Level 1) test scenarios."""
    
    def __init__(self, config: ScenarioConfig, debug: bool = False, watch: bool = False):
        """Initialize the basic scenario runner.
        
        Args:
            config: Scenario configuration
            debug: Enable debug mode with technical details
            watch: Enable watch mode for real-time monitoring
        """
        self.config = config
        self.debug = debug
        self.watch = watch
        self.console = Console() if (debug or watch) else None
        self.auth_provider = self._create_auth_provider()
        self.http_client: Optional[HTTPClient] = None
    
    def _create_auth_provider(self) -> AuthBase:
        """Create authentication provider based on configuration.
        
        Returns:
            Authentication provider instance
            
        Raises:
            ValueError: If unsupported auth provider is specified
        """
        if self.config.auth.provider == AuthProvider.SUPABASE:
            return SupabaseAuth(self.config.auth)
        elif self.config.auth.provider == AuthProvider.JWT:
            return JWTAuth(self.config.auth)
        elif self.config.auth.provider == AuthProvider.NOOP:
            return NoopAuth(self.config.auth)
        else:
            raise ValueError(f"Unsupported auth provider: {self.config.auth.provider}")
    
    def _debug_log(self, message: str, details: Optional[Dict] = None):
        """Log debug information for basic scenarios.
        
        Args:
            message: Main debug message
            details: Optional dictionary of additional details
        """
        if not self.debug or not self.console:
            return
        
        self.console.print(f"🔍 [bold blue]DEBUG[/bold blue] {message}")
        if details:
            for key, value in details.items():
                self.console.print(f"   ├─ {key}: {value}")
        self.console.print("")
    
    def _watch_log(self, message: str):
        """Log watch information for basic scenarios.
        
        Args:
            message: Watch message to display
        """
        if not self.watch or not self.console:
            return
        
        self.console.print(message)
    
    async def run(self) -> ScenarioReport:
        """Run the basic scenario and return results.
        
        Returns:
            Complete scenario report with all step results
        """
        report = ScenarioReport(
            scenario_name=self.config.name,
            passed=True,
            total_steps=len(self.config.steps),
            passed_steps=0,
            failed_steps=0,
            total_duration_ms=0.0,
            step_results=[],
            started_at=datetime.now(),
        )
        
        # Initialize HTTP client
        auth_headers = await self.auth_provider.get_headers()
        self.http_client = HTTPClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay_seconds,
            default_headers=auth_headers,
        )
        
        self._debug_log("Basic scenario initialized", {
            "scenario_name": self.config.name,
            "base_url": self.config.base_url,
            "total_steps": len(self.config.steps),
            "auth_provider": self.config.auth.provider.value
        })
        
        self._watch_log(f"📋 [bold green]BASIC SCENARIO[/bold green] - {self.config.name}")
        self._watch_log(f"🔢 Total steps: {len(self.config.steps)}")
        if self.watch:
            self._watch_log("")
        
        try:
            # Execute each step
            for i, step in enumerate(self.config.steps):
                self._watch_log(f"👤 [bold cyan]Step {i+1}:[/bold cyan] {step.user}")
                self._debug_log(f"Executing step {i+1}", {
                    "user_message": step.user,
                    "expect_contains": step.expect_contains,
                    "expect_regex": step.expect_regex,
                    "expect_equals": step.expect_equals,
                    "expect_not_contains": step.expect_not_contains
                })
                step_result = await self._execute_step(i, step)
                report.step_results.append(step_result)
                report.total_duration_ms += step_result.latency_ms
                
                # Log step result
                status_emoji = "✅" if step_result.passed else "❌"
                self._watch_log(f"{status_emoji} [bold]Step {i+1}:[/bold] {'PASSED' if step_result.passed else 'FAILED'} ({step_result.latency_ms:.1f}ms)")
                
                self._debug_log(f"Step {i+1} completed", {
                    "passed": step_result.passed,
                    "latency_ms": step_result.latency_ms,
                    "response_length": len(step_result.response),
                    "assertions_passed": sum(1 for a in step_result.assertions if a.passed),
                    "assertions_total": len(step_result.assertions),
                    "error": step_result.error
                })
                
                if step_result.passed:
                    report.passed_steps += 1
                else:
                    report.failed_steps += 1
                    report.passed = False
            
            # Log final summary
            if self.watch:
                self._watch_log("")
                self._watch_log("📊 [bold green]SCENARIO COMPLETE[/bold green]")
                status = "✅ SUCCESS" if report.passed else "❌ FAILED"
                self._watch_log(f"🏁 Status: {status}")
                self._watch_log(f"🔢 Steps: {report.passed_steps}/{report.total_steps} passed")
                self._watch_log(f"⏱️  Duration: {report.total_duration_ms/1000:.1f}s")
            
            self._debug_log("Basic scenario completed", {
                "passed": report.passed,
                "total_steps": report.total_steps,
                "passed_steps": report.passed_steps,
                "total_duration_ms": report.total_duration_ms
            })
            
            report.completed_at = datetime.now()
            
        except Exception as e:
            report.error = str(e)
            report.passed = False
            report.completed_at = datetime.now()
            
            self._watch_log(f"❌ [bold red]ERROR[/bold red] - {str(e)}")
            self._debug_log("Basic scenario failed", {
                "error": str(e),
                "error_type": type(e).__name__,
                "steps_completed": len(report.step_results)
            })
        
        finally:
            # Clean up HTTP client
            if self.http_client:
                await self.http_client.close()
        
        return report
    
    async def _execute_step(self, step_index: int, step: Step) -> StepResult:
        """Execute a single test step.
        
        Args:
            step_index: Index of the step in the scenario
            step: Step configuration
            
        Returns:
            Result of executing the step
        """
        step_result = StepResult(
            step_index=step_index,
            user_message=step.user,
            response="",
            latency_ms=0.0,
            assertions=[],
            passed=False,
            timestamp=datetime.now(),
        )
        
        try:
            # Make HTTP request to the API
            response = await self._make_api_request(step.user, step.timeout_seconds)
            step_result.response = response.content
            step_result.latency_ms = response.latency_ms
            
            # Validate assertions
            step_result.assertions = self._validate_assertions(step, response.content)
            step_result.passed = all(assertion.passed for assertion in step_result.assertions)
            
        except Exception as e:
            step_result.error = str(e)
            step_result.passed = False
        
        return step_result
    
    async def _make_api_request(self, user_message: str, timeout: Optional[int] = None) -> HTTPResponse:
        """Make API request with user message.
        
        Args:
            user_message: User message to send to API
            timeout: Request timeout in seconds
            
        Returns:
            HTTP response
        """
        # Prepare request payload
        # This is a simple example - real APIs may have different formats
        payload = {
            "message": user_message,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Make POST request to the API
        response = await self.http_client.post(
            url="",  # Use base URL
            json=payload,
            max_retries=self.config.max_retries,
        )
        
        return response
    
    def _validate_assertions(self, step: Step, response_content: str) -> List[AssertionResult]:
        """Validate all assertions for a step.
        
        Args:
            step: Step configuration with assertions
            response_content: Response content to validate
            
        Returns:
            List of assertion results
        """
        assertions = []
        
        # Check contains assertions
        if step.expect_contains:
            for expected_text in step.expect_contains:
                assertion = self._validate_contains(expected_text, response_content)
                assertions.append(assertion)
        
        # Check regex assertions
        if step.expect_regex:
            assertion = self._validate_regex(step.expect_regex, response_content)
            assertions.append(assertion)
        
        # Check equals assertions
        if step.expect_equals:
            assertion = self._validate_equals(step.expect_equals, response_content)
            assertions.append(assertion)
        
        # Check not contains assertions
        if step.expect_not_contains:
            for forbidden_text in step.expect_not_contains:
                assertion = self._validate_not_contains(forbidden_text, response_content)
                assertions.append(assertion)
        
        return assertions
    
    def _validate_contains(self, expected: str, actual: str) -> AssertionResult:
        """Validate that response contains expected text.
        
        Args:
            expected: Text that should be present
            actual: Actual response content
            
        Returns:
            Assertion result
        """
        passed = expected.lower() in actual.lower()
        return AssertionResult(
            assertion_type=AssertionType.CONTAINS,
            expected=expected,
            actual=actual,
            passed=passed,
            error_message=None if passed else f"Expected text '{expected}' not found in response",
        )
    
    def _validate_regex(self, pattern: str, actual: str) -> AssertionResult:
        """Validate that response matches regex pattern.
        
        Args:
            pattern: Regex pattern to match
            actual: Actual response content
            
        Returns:
            Assertion result
        """
        try:
            match = re.search(pattern, actual)
            passed = match is not None
            return AssertionResult(
                assertion_type=AssertionType.REGEX,
                expected=pattern,
                actual=actual,
                passed=passed,
                error_message=None if passed else f"Response does not match regex pattern: {pattern}",
            )
        except re.error as e:
            return AssertionResult(
                assertion_type=AssertionType.REGEX,
                expected=pattern,
                actual=actual,
                passed=False,
                error_message=f"Invalid regex pattern: {str(e)}",
            )
    
    def _validate_equals(self, expected: str, actual: str) -> AssertionResult:
        """Validate that response equals expected text exactly.
        
        Args:
            expected: Expected text
            actual: Actual response content
            
        Returns:
            Assertion result
        """
        passed = expected.strip() == actual.strip()
        return AssertionResult(
            assertion_type=AssertionType.EQUALS,
            expected=expected,
            actual=actual,
            passed=passed,
            error_message=None if passed else f"Response does not equal expected text",
        )
    
    def _validate_not_contains(self, forbidden: str, actual: str) -> AssertionResult:
        """Validate that response does not contain forbidden text.
        
        Args:
            forbidden: Text that should not be present
            actual: Actual response content
            
        Returns:
            Assertion result
        """
        passed = forbidden.lower() not in actual.lower()
        return AssertionResult(
            assertion_type=AssertionType.NOT_CONTAINS,
            expected=forbidden,
            actual=actual,
            passed=passed,
            error_message=None if passed else f"Forbidden text '{forbidden}' found in response",
        ) 