# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Markdown report generator for ReplicantX.

This module provides functionality to generate human-readable Markdown reports
from test scenario results, including tables of steps and summary information.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Union

from ..models import ScenarioReport, TestSuiteReport, StepResult, AssertionResult


class MarkdownReporter:
    """Generates Markdown reports from test results."""
    
    def __init__(self):
        """Initialize the Markdown reporter."""
        pass
    
    def write_scenario_report(self, report: ScenarioReport, output_path: Union[str, Path]) -> None:
        """Write a single scenario report to Markdown file.
        
        Args:
            report: Scenario report to write
            output_path: Path to write the report file
        """
        content = self._generate_scenario_markdown(report)
        self._write_to_file(content, output_path)
    
    def write_test_suite_report(self, report: TestSuiteReport, output_path: Union[str, Path]) -> None:
        """Write a test suite report to Markdown file.
        
        Args:
            report: Test suite report to write
            output_path: Path to write the report file
        """
        content = self._generate_test_suite_markdown(report)
        self._write_to_file(content, output_path)
    
    def _generate_scenario_markdown(self, report: ScenarioReport) -> str:
        """Generate Markdown content for a single scenario.
        
        Args:
            report: Scenario report
            
        Returns:
            Markdown content as string
        """
        lines = []
        
        # Header
        lines.append(f"# Test Scenario: {report.scenario_name}")
        lines.append("")
        
        # Summary
        status_emoji = "✅" if report.passed else "❌"
        lines.append(f"**Status:** {status_emoji} {'PASSED' if report.passed else 'FAILED'}")
        lines.append(f"**Total Steps:** {report.total_steps}")
        lines.append(f"**Passed Steps:** {report.passed_steps}")
        lines.append(f"**Failed Steps:** {report.failed_steps}")
        lines.append(f"**Success Rate:** {report.success_rate:.1f}%")
        lines.append(f"**Total Duration:** {report.duration_seconds:.2f}s")
        lines.append(f"**Started:** {report.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if report.completed_at:
            lines.append(f"**Completed:** {report.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Complete conversation history for agent scenarios
        if hasattr(report, 'conversation_history') and report.conversation_history:
            lines.append(report.conversation_history)
            lines.append("")
        
        # Error message if any
        if report.error:
            lines.append("## Summary")
            lines.append(f"```")
            lines.append(report.error)
            lines.append("```")
            lines.append("")
        
        # Steps table
        if report.step_results:
            lines.append("## Test Steps")
            lines.append("")
            lines.append("| Step | User Message | Response | Latency | Assertions | Status |")
            lines.append("|------|-------------|----------|---------|------------|--------|")
            
            for step in report.step_results:
                status_emoji = "✅" if step.passed else "❌"
                latency_str = f"{step.latency_ms:.0f}ms"
                
                # Truncate long messages for table readability
                user_msg = self._truncate_text(step.user_message, 50)
                response_text = self._truncate_text(step.response, 50)
                
                # Format assertions
                assertions_str = self._format_assertions_summary(step.assertions)
                
                lines.append(f"| {step.step_index + 1} | {user_msg} | {response_text} | {latency_str} | {assertions_str} | {status_emoji} |")
            
            lines.append("")
        
        # Detailed step results
        if report.step_results:
            lines.append("## Detailed Step Results")
            lines.append("")
            
            for step in report.step_results:
                lines.append(f"### Step {step.step_index + 1}")
                
                status_emoji = "✅" if step.passed else "❌"
                lines.append(f"**Status:** {status_emoji} {'PASSED' if step.passed else 'FAILED'}")
                lines.append(f"**Latency:** {step.latency_ms:.2f}ms")
                lines.append(f"**Timestamp:** {step.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                lines.append("")
                
                # User message
                lines.append("**User Message:**")
                lines.append(f"```")
                lines.append(step.user_message)
                lines.append("```")
                lines.append("")
                
                # Response
                lines.append("**Response:**")
                lines.append(f"```")
                lines.append(step.response)
                lines.append("```")
                lines.append("")
                
                # Assertions
                if step.assertions:
                    lines.append("**Assertions:**")
                    for assertion in step.assertions:
                        assertion_emoji = "✅" if assertion.passed else "❌"
                        lines.append(f"- {assertion_emoji} {assertion.assertion_type.value}: {assertion.expected}")
                        if not assertion.passed and assertion.error_message:
                            lines.append(f"  - Error: {assertion.error_message}")
                    lines.append("")
                
                # Error message
                if step.error:
                    lines.append("**Error:**")
                    lines.append(f"```")
                    lines.append(step.error)
                    lines.append("```")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
        
        return "\n".join(lines)
    
    def _generate_test_suite_markdown(self, report: TestSuiteReport) -> str:
        """Generate Markdown content for a test suite.
        
        Args:
            report: Test suite report
            
        Returns:
            Markdown content as string
        """
        lines = []
        
        # Header
        lines.append("# ReplicantX Test Suite Report")
        lines.append("")
        
        # Summary
        status_emoji = "✅" if report.passed_scenarios == report.total_scenarios else "❌"
        lines.append(f"**Overall Status:** {status_emoji} {report.passed_scenarios}/{report.total_scenarios} scenarios passed")
        lines.append(f"**Total Scenarios:** {report.total_scenarios}")
        lines.append(f"**Passed Scenarios:** {report.passed_scenarios}")
        lines.append(f"**Failed Scenarios:** {report.failed_scenarios}")
        lines.append(f"**Success Rate:** {report.success_rate:.1f}%")
        lines.append(f"**Total Duration:** {report.duration_seconds:.2f}s")
        lines.append(f"**Started:** {report.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if report.completed_at:
            lines.append(f"**Completed:** {report.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Scenarios summary table
        if report.scenario_reports:
            lines.append("## Scenarios Summary")
            lines.append("")
            lines.append("| Scenario | Steps | Success Rate | Duration | Status |")
            lines.append("|----------|-------|-------------|----------|--------|")
            
            for scenario in report.scenario_reports:
                status_emoji = "✅" if scenario.passed else "❌"
                duration_str = f"{scenario.duration_seconds:.2f}s"
                
                scenario_name = self._truncate_text(scenario.scenario_name, 40)
                steps_str = f"{scenario.passed_steps}/{scenario.total_steps}"
                
                lines.append(f"| {scenario_name} | {steps_str} | {scenario.success_rate:.1f}% | {duration_str} | {status_emoji} |")
            
            lines.append("")
        
        # Individual scenario reports
        if report.scenario_reports:
            lines.append("## Individual Scenario Reports")
            lines.append("")
            
            for scenario in report.scenario_reports:
                lines.append(f"### {scenario.scenario_name}")
                
                status_emoji = "✅" if scenario.passed else "❌"
                lines.append(f"**Status:** {status_emoji} {'PASSED' if scenario.passed else 'FAILED'}")
                lines.append(f"**Steps:** {scenario.passed_steps}/{scenario.total_steps}")
                lines.append(f"**Success Rate:** {scenario.success_rate:.1f}%")
                lines.append(f"**Duration:** {scenario.duration_seconds:.2f}s")
                lines.append("")
                
                # Complete conversation history for agent scenarios
                if hasattr(scenario, 'conversation_history') and scenario.conversation_history:
                    lines.append("**Complete Conversation:**")
                    lines.append("")
                    lines.append(scenario.conversation_history)
                    lines.append("")
                
                # Error message
                if scenario.error:
                    lines.append("**Summary:**")
                    lines.append(f"```")
                    lines.append(scenario.error)
                    lines.append("```")
                    lines.append("")
                
                # Failed steps summary
                failed_steps = [step for step in scenario.step_results if not step.passed]
                if failed_steps:
                    lines.append("**Failed Steps:**")
                    for step in failed_steps:
                        lines.append(f"- Step {step.step_index + 1}: {self._truncate_text(step.user_message, 80)}")
                        if step.error:
                            lines.append(f"  - Error: {step.error}")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
        
        # Footer
        lines.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by ReplicantX*")
        
        return "\n".join(lines)
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length with ellipsis.
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
    
    def _format_assertions_summary(self, assertions: List[AssertionResult]) -> str:
        """Format assertions for summary display.
        
        Args:
            assertions: List of assertion results
            
        Returns:
            Formatted assertions summary
        """
        if not assertions:
            return "None"
        
        passed = sum(1 for a in assertions if a.passed)
        total = len(assertions)
        
        if passed == total:
            return f"✅ {passed}/{total}"
        else:
            return f"❌ {passed}/{total}"
    
    def _write_to_file(self, content: str, output_path: Union[str, Path]) -> None:
        """Write content to file.
        
        Args:
            content: Content to write
            output_path: Path to write to
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content) 