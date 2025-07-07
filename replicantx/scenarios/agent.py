# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Agent scenario runner for ReplicantX.

This module implements Level 2 (Advanced) test scenarios where a Pydantic-based
Replicant agent converses intelligently with APIs using configurable facts and
system prompts to achieve specific goals.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from ..auth import AuthBase, SupabaseAuth, JWTAuth, NoopAuth
from ..models import (
    ScenarioConfig, ScenarioReport, StepResult, AssertionResult,
    AssertionType, AuthProvider, Message
)
from ..tools.http_client import HTTPClient, HTTPResponse
from .replicant import ReplicantAgent
from rich.console import Console


class AgentScenarioRunner:
    """Runner for Replicant agent-driven (Level 2) test scenarios."""
    
    def __init__(self, config: ScenarioConfig, debug: bool = False, watch: bool = False):
        """Initialize the agent scenario runner.
        
        Args:
            config: Scenario configuration with Replicant agent setup
            debug: Enable debug mode with technical details
            watch: Enable watch mode for real-time monitoring
        """
        self.config = config
        self.debug = debug
        self.watch = watch
        self.console = Console() if (debug or watch) else None
        self.auth_provider = self._create_auth_provider()
        self.http_client: Optional[HTTPClient] = None
        self.replicant_agent: Optional[ReplicantAgent] = None
    
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
        """Log debug information with technical details.
        
        Args:
            message: Main debug message
            details: Optional dictionary of additional details
        """
        if not self.debug or not self.console:
            return
        
        self.console.print(f"🔍 [bold blue]DEBUG[/bold blue] {message}")
        if details:
            for key, value in details.items():
                # Truncate long values for readability
                if isinstance(value, str) and len(value) > 100:
                    display_value = f"{value[:100]}..."
                else:
                    display_value = value
                self.console.print(f"   ├─ {key}: {display_value}")
        self.console.print("")
    
    def _watch_log(self, message: str, timestamp: Optional[datetime] = None):
        """Log watch information for conversation monitoring.
        
        Args:
            message: Watch message to display
            timestamp: Optional timestamp (uses current time if not provided)
        """
        if not self.watch or not self.console:
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        time_str = timestamp.strftime("%H:%M:%S")
        self.console.print(f"[{time_str}] {message}")
    
    async def run(self) -> ScenarioReport:
        """Run the agent scenario and return results.
        
        Returns:
            Complete scenario report with all step results
        """
        if not self.config.replicant:
            raise ValueError("Agent scenarios require replicant configuration")
        
        report = ScenarioReport(
            scenario_name=self.config.name,
            passed=True,
            total_steps=0,
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
        
        self._debug_log("HTTP Client initialized", {
            "base_url": self.config.base_url,
            "timeout": f"{self.config.timeout_seconds}s",
            "max_retries": self.config.max_retries,
            "auth_provider": self.config.auth.provider.value,
            "auth_headers": f"{len(auth_headers)} headers" if auth_headers else "none"
        })
        
        # Initialize Replicant agent
        self.replicant_agent = ReplicantAgent.create(self.config.replicant)
        
        self._debug_log("Replicant Agent initialized", {
            "goal": self.config.replicant.goal,
            "facts_count": len(self.config.replicant.facts),
            "facts": str(self.config.replicant.facts),
            "model": self.config.replicant.llm.model,
            "temperature": self.config.replicant.llm.temperature,
            "max_tokens": self.config.replicant.llm.max_tokens,
            "max_turns": self.config.replicant.max_turns
        })
        
        # Initialize watch mode
        if self.watch:
            self._watch_log("👥 [bold green]LIVE CONVERSATION[/bold green] - Starting agent scenario")
            self._watch_log(f"🎯 Goal: {self.config.replicant.goal}")
            self._watch_log(f"📝 Facts: {len(self.config.replicant.facts)} items available")
            self._watch_log("")
        
        try:
            # Start conversation with initial message
            current_message = self.replicant_agent.get_initial_message()
            step_index = 0
            
            self._debug_log("Starting conversation", {
                "initial_message": current_message,
                "step_index": step_index
            })
            
            self._watch_log(f"👤 [bold cyan]User:[/bold cyan] {current_message}")
            
            # Record initial message in conversation history
            from ..models import Message
            initial_message = Message(
                role="user",
                content=current_message,
                timestamp=datetime.now()
            )
            self.replicant_agent.state.conversation_history.append(initial_message)
            
            # Continue conversation until completion or limits reached
            while self.replicant_agent.should_continue_conversation():
                self._debug_log(f"Executing conversation step {step_index + 1}", {
                    "user_message": current_message,
                    "turn_count": self.replicant_agent.state.turn_count,
                    "goal_achieved": self.replicant_agent.state.goal_achieved
                })
                
                self._watch_log(f"⏱️  [dim]Waiting for response...[/dim]")
                
                # Execute conversation step
                step_result = await self._execute_conversation_step(step_index, current_message)
                report.step_results.append(step_result)
                report.total_duration_ms += step_result.latency_ms
                
                # Log step completion
                status_emoji = "✅" if step_result.passed else "❌"
                self._watch_log(f"{status_emoji} [bold]Step {step_index + 1}:[/bold] {'PASSED' if step_result.passed else 'FAILED'} ({step_result.latency_ms:.1f}ms)")
                
                self._debug_log(f"Step {step_index + 1} completed", {
                    "passed": step_result.passed,
                    "latency_ms": step_result.latency_ms,
                    "response_length": len(step_result.response),
                    "assertions_count": len(step_result.assertions),
                    "error": step_result.error
                })
                
                # Update counters
                report.total_steps += 1
                if step_result.passed:
                    report.passed_steps += 1
                else:
                    report.failed_steps += 1
                    report.passed = False
                
                # If step failed, break the conversation
                if not step_result.passed:
                    self._watch_log(f"❌ [bold red]Conversation stopped[/bold red] - Step {step_index + 1} failed")
                    self._debug_log("Conversation stopped due to step failure")
                    break
                
                # Generate next message from API response
                if step_result.response:
                    # Parse the response to extract the final message
                    parsed_response = self._parse_streaming_response(step_result.response)
                    
                    self._watch_log(f"🤖 [bold magenta]Assistant:[/bold magenta] {parsed_response}")
                    
                    self._debug_log("Processing API response", {
                        "raw_response_length": len(step_result.response),
                        "parsed_response_length": len(parsed_response),
                        "parsed_response": parsed_response
                    })
                    
                    current_message = await self.replicant_agent.process_api_response(parsed_response)
                    
                    self._debug_log("Generated next user message", {
                        "next_message": current_message,
                        "conversation_length": len(self.replicant_agent.state.conversation_history)
                    })
                    
                    self._watch_log(f"👤 [bold cyan]User:[/bold cyan] {current_message}")
                else:
                    # No response, can't continue
                    self._watch_log("❌ [bold red]No response received[/bold red] - Ending conversation")
                    self._debug_log("No response received, ending conversation")
                    break
                
                step_index += 1
                
                # Safety check for infinite loops
                if step_index > 50:
                    report.error = "Maximum conversation steps exceeded"
                    report.passed = False
                    break
            
            # Add conversation summary to report
            conversation_summary = self.replicant_agent.get_conversation_summary()
            report.error = report.error or self._format_conversation_summary(conversation_summary)
            
            # Add conversation history to the last step result for reporting
            if report.step_results and self.replicant_agent:
                conversation_history = self._format_full_conversation()
                # Store conversation in the report for detailed display
                report.conversation_history = conversation_history
            
            # Log final summary for watch mode
            if self.watch:
                self._watch_log("")
                self._watch_log("📊 [bold green]CONVERSATION COMPLETE[/bold green]")
                status = "✅ SUCCESS" if report.passed else "❌ FAILED"
                self._watch_log(f"🏁 Status: {status}")
                self._watch_log(f"🔢 Steps: {report.passed_steps}/{report.total_steps} passed")
                self._watch_log(f"⏱️  Duration: {report.total_duration_ms/1000:.1f}s")
                self._watch_log(f"🎯 Goal achieved: {'Yes' if conversation_summary.get('goal_achieved', False) else 'No'}")
                self._watch_log(f"📝 Facts used: {conversation_summary.get('facts_used', 0)}")
                self._watch_log(f"💬 Total turns: {conversation_summary.get('total_turns', 0)}")
            
            self._debug_log("Scenario completed successfully", {
                "passed": report.passed,
                "total_steps": report.total_steps,
                "passed_steps": report.passed_steps,
                "total_duration_ms": report.total_duration_ms,
                "conversation_summary": conversation_summary
            })
            
            report.completed_at = datetime.now()
            
        except Exception as e:
            report.error = str(e)
            report.passed = False
            report.completed_at = datetime.now()
            
            self._watch_log(f"❌ [bold red]ERROR[/bold red] - {str(e)}")
            self._debug_log("Scenario failed with exception", {
                "error": str(e),
                "error_type": type(e).__name__,
                "steps_completed": len(report.step_results)
            })
        
        finally:
            # Clean up HTTP client
            if self.http_client:
                await self.http_client.close()
        
        return report
    
    async def _execute_conversation_step(self, step_index: int, user_message: str) -> StepResult:
        """Execute a single conversation step.
        
        Args:
            step_index: Index of the step in the conversation
            user_message: User message to send
            
        Returns:
            Result of executing the step
        """
        step_result = StepResult(
            step_index=step_index,
            user_message=user_message,
            response="",
            latency_ms=0.0,
            assertions=[],
            passed=False,
            timestamp=datetime.now(),
        )
        
        try:
            # Make HTTP request to the API
            self._debug_log("Making HTTP request", {
                "user_message": user_message,
                "base_url": self.config.base_url,
                "timeout": f"{self.config.timeout_seconds}s"
            })
            
            response = await self._make_api_request(user_message)
            step_result.response = response.content
            step_result.latency_ms = response.latency_ms
            
            self._debug_log("HTTP response received", {
                "status_code": response.status_code if hasattr(response, 'status_code') else "unknown",
                "latency_ms": response.latency_ms,
                "content_length": len(response.content),
                "content_preview": response.content[:200]
            })
            
            # Validate the response
            step_result.assertions = self._validate_api_response(response.content, user_message)
            step_result.passed = all(assertion.passed for assertion in step_result.assertions)
            
            self._debug_log("Response validation completed", {
                "total_assertions": len(step_result.assertions),
                "passed_assertions": sum(1 for a in step_result.assertions if a.passed),
                "failed_assertions": sum(1 for a in step_result.assertions if not a.passed),
                "overall_passed": step_result.passed
            })
            
            # Log individual assertion results
            for i, assertion in enumerate(step_result.assertions):
                status = "✅ PASS" if assertion.passed else "❌ FAIL"
                self._debug_log(f"Assertion {i+1}: {assertion.assertion_type.value}", {
                    "status": status,
                    "expected": assertion.expected,
                    "error": assertion.error_message if not assertion.passed else None
                })
            
        except Exception as e:
            step_result.error = str(e)
            step_result.passed = False
            self._debug_log("HTTP request failed", {
                "error": str(e),
                "user_message": user_message
            })
        
        return step_result
    
    async def _make_api_request(self, user_message: str) -> HTTPResponse:
        """Make API request with user message.
        
        Args:
            user_message: User message to send to API
            
        Returns:
            HTTP response
        """
        # Prepare request payload
        # Include conversation history for context
        conversation_history = []
        if self.replicant_agent:
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in self.replicant_agent.state.conversation_history[-10:]  # Last 10 messages
            ]
        
        payload = {
            "message": user_message,
            "timestamp": datetime.now().isoformat(),
            "conversation_history": conversation_history
        }
        
        self._debug_log("HTTP request payload", {
            "message": user_message,
            "conversation_history_length": len(conversation_history),
            "payload_size": f"{len(str(payload))} chars",
            "full_payload": str(payload) if len(str(payload)) < 500 else f"{str(payload)[:500]}..."
        })
        
        # Make POST request to the API
        response = await self.http_client.post(
            url="",  # Use base URL
            json=payload,
            max_retries=self.config.max_retries,
        )
        
        return response
    
    def _validate_api_response(self, response_content: str, user_message: str) -> List[AssertionResult]:
        """Validate API response with intelligent criteria.
        
        Args:
            response_content: Response content to validate
            user_message: User message that prompted this response
            
        Returns:
            List of assertion results
        """
        assertions = []
        
        # Parse streaming response if needed
        parsed_response = self._parse_streaming_response(response_content)
        
        # Basic validation: response should not be empty
        if parsed_response.strip():
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="non-empty response",
                actual=parsed_response,
                passed=True,
                error_message=None,
            ))
        else:
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="non-empty response",
                actual=parsed_response,
                passed=False,
                error_message="API returned empty response",
            ))
            return assertions  # No point in further validation
        
        # Response should be reasonably long for meaningful conversation
        min_length = 10
        if len(parsed_response.strip()) >= min_length:
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="meaningful response",
                actual=parsed_response,
                passed=True,
                error_message=None,
            ))
        else:
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="meaningful response",
                actual=parsed_response,
                passed=False,
                error_message=f"Response too short (less than {min_length} characters)",
            ))
        
        # Check for appropriate conversational patterns
        response_lower = parsed_response.lower()
        user_lower = user_message.lower()
        
        # If user asks a question, response should provide some form of answer or follow-up
        if "?" in user_message:
            # Response should either answer or ask for clarification
            has_answer_pattern = any(pattern in response_lower for pattern in [
                "yes", "no", "sure", "of course", "certainly", "that's",
                "i can", "i will", "let me", "i need", "could you", "what", "when", "where", "how"
            ])
            
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="conversational response to question",
                actual=parsed_response,
                passed=has_answer_pattern,
                error_message=None if has_answer_pattern else "Response doesn't seem to address the user's question",
            ))
        
        # Check for politeness and conversational tone (if enabled)
        if self.config.validate_politeness:
            has_polite_tone = any(pattern in response_lower for pattern in [
                "thank", "please", "great", "perfect", "wonderful", "excellent",
                "i'd be happy", "i can help", "let me help", "how can i", "ready to help",
                "i'm ready", "assist you", "help you", "happy to", "here to help",
                "would you prefer", "what would you like", "which", "do you", "can you",
                "let me know", "please tell me", "what type", "what kind", "what category",
                "how many", "will you be", "are you", "have you", "would you", "do you need",
                "any", "prefer", "select", "choose", "pick", "option", "details", "information"
            ])
            
            assertions.append(AssertionResult(
                assertion_type=AssertionType.CONTAINS,
                expected="polite conversational tone",
                actual=parsed_response,
                passed=has_polite_tone,
                error_message=None if has_polite_tone else "Response lacks conversational/polite tone",
            ))
        
        return assertions
    
    def _parse_streaming_response(self, response_content: str) -> str:
        """Parse streaming response and extract the final message.
        
        Args:
            response_content: Raw response content that may be streaming format
            
        Returns:
            Extracted final message or original content if not streaming
        """
        import json
        import re
        
        # Check if this looks like a streaming response (contains "data:" lines)
        if "data:" not in response_content:
            return response_content
        
        try:
            # Split into lines and process each data line
            lines = response_content.strip().split('\n')
            final_response = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('data:'):
                    # Extract JSON from "data: {json}"
                    json_str = line[5:].strip()
                    if json_str:
                        try:
                            data = json.loads(json_str)
                            # Look for final response
                            if isinstance(data, dict):
                                if data.get('type') == 'final' and 'response' in data:
                                    final_response = data['response']
                                # Also check for direct response field
                                elif 'response' in data and not final_response:
                                    final_response = data['response']
                        except json.JSONDecodeError:
                            continue
            
            # Return the final response if found, otherwise the original content
            return final_response if final_response else response_content
            
        except Exception:
            # If parsing fails, return original content
            return response_content
    
    def _format_conversation_summary(self, summary: Dict) -> str:
        """Format conversation summary for the report.
        
        Args:
            summary: Conversation summary from Replicant agent
            
        Returns:
            Formatted summary string
        """
        lines = [
            f"Conversation Summary:",
            f"- Goal: {summary['goal']}",
            f"- Total turns: {summary['total_turns']}",
            f"- Goal achieved: {summary['goal_achieved']}",
            f"- Facts used: {summary['facts_used']}",
            f"- Conversation length: {summary['conversation_length']} messages"
        ]
        return "\n".join(lines)
    
    def _format_full_conversation(self) -> str:
        """Format the complete conversation history for reporting.
        
        Returns:
            Formatted conversation history
        """
        if not self.replicant_agent or not self.replicant_agent.state.conversation_history:
            return "No conversation history available."
        
        lines = []
        lines.append("## Complete Conversation")
        lines.append("")
        
        for i, message in enumerate(self.replicant_agent.state.conversation_history):
            if message.role == "user":
                lines.append(f"**👤 User (Turn {(i//2)+1}):**")
                lines.append(f"> {message.content}")
            else:  # assistant
                lines.append(f"**🤖 Assistant:**")
                lines.append(f"> {message.content}")
            lines.append("")
        
        return "\n".join(lines) 