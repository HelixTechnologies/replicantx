# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
JSON report generator for ReplicantX.

This module provides functionality to generate machine-readable JSON reports
from test scenario results for programmatic analysis and integration.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Union

from ..models import ScenarioReport, TestSuiteReport


class JSONReporter:
    """Generates JSON reports from test results."""
    
    def __init__(self, indent: int = 2):
        """Initialize the JSON reporter.
        
        Args:
            indent: Number of spaces for JSON indentation
        """
        self.indent = indent
    
    def write_scenario_report(self, report: ScenarioReport, output_path: Union[str, Path]) -> None:
        """Write a single scenario report to JSON file.
        
        Args:
            report: Scenario report to write
            output_path: Path to write the report file
        """
        data = self._serialize_scenario_report(report)
        self._write_to_file(data, output_path)
    
    def write_test_suite_report(self, report: TestSuiteReport, output_path: Union[str, Path]) -> None:
        """Write a test suite report to JSON file.
        
        Args:
            report: Test suite report to write
            output_path: Path to write the report file
        """
        data = self._serialize_test_suite_report(report)
        self._write_to_file(data, output_path)
    
    def _serialize_scenario_report(self, report: ScenarioReport) -> Dict[str, Any]:
        """Serialize a scenario report to dictionary.
        
        Args:
            report: Scenario report to serialize
            
        Returns:
            Dictionary representation of the report
        """
        return {
            "report_type": "scenario",
            "scenario_name": report.scenario_name,
            "status": "passed" if report.passed else "failed",
            "summary": {
                "total_steps": report.total_steps,
                "passed_steps": report.passed_steps,
                "failed_steps": report.failed_steps,
                "success_rate": report.success_rate,
                "total_duration_ms": report.total_duration_ms,
                "duration_seconds": report.duration_seconds,
            },
            "timing": {
                "started_at": report.started_at.isoformat(),
                "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            },
            "error": report.error,
            "step_results": [
                self._serialize_step_result(step) for step in report.step_results
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator": "ReplicantX JSON Reporter",
                "version": "1.0"
            }
        }
    
    def _serialize_test_suite_report(self, report: TestSuiteReport) -> Dict[str, Any]:
        """Serialize a test suite report to dictionary.
        
        Args:
            report: Test suite report to serialize
            
        Returns:
            Dictionary representation of the report
        """
        return {
            "report_type": "test_suite",
            "status": "passed" if report.passed_scenarios == report.total_scenarios else "failed",
            "summary": {
                "total_scenarios": report.total_scenarios,
                "passed_scenarios": report.passed_scenarios,
                "failed_scenarios": report.failed_scenarios,
                "success_rate": report.success_rate,
                "total_duration_ms": report.total_duration_ms,
                "duration_seconds": report.duration_seconds,
            },
            "timing": {
                "started_at": report.started_at.isoformat(),
                "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            },
            "scenario_reports": [
                self._serialize_scenario_report(scenario) for scenario in report.scenario_reports
            ],
            "statistics": {
                "total_steps": sum(scenario.total_steps for scenario in report.scenario_reports),
                "total_passed_steps": sum(scenario.passed_steps for scenario in report.scenario_reports),
                "total_failed_steps": sum(scenario.failed_steps for scenario in report.scenario_reports),
                "average_scenario_duration": (
                    report.total_duration_ms / report.total_scenarios
                    if report.total_scenarios > 0 else 0
                ),
                "fastest_scenario": self._get_fastest_scenario(report.scenario_reports),
                "slowest_scenario": self._get_slowest_scenario(report.scenario_reports),
            },
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator": "ReplicantX JSON Reporter",
                "version": "1.0"
            }
        }
    
    def _serialize_step_result(self, step: 'StepResult') -> Dict[str, Any]:
        """Serialize a step result to dictionary.
        
        Args:
            step: Step result to serialize
            
        Returns:
            Dictionary representation of the step
        """
        return {
            "step_index": step.step_index,
            "user_message": step.user_message,
            "response": step.response,
            "latency_ms": step.latency_ms,
            "status": "passed" if step.passed else "failed",
            "timestamp": step.timestamp.isoformat(),
            "error": step.error,
            "assertions": [
                self._serialize_assertion_result(assertion) for assertion in step.assertions
            ]
        }
    
    def _serialize_assertion_result(self, assertion: 'AssertionResult') -> Dict[str, Any]:
        """Serialize an assertion result to dictionary.
        
        Args:
            assertion: Assertion result to serialize
            
        Returns:
            Dictionary representation of the assertion
        """
        return {
            "assertion_type": assertion.assertion_type.value,
            "expected": assertion.expected,
            "actual": assertion.actual,
            "status": "passed" if assertion.passed else "failed",
            "error_message": assertion.error_message,
        }
    
    def _get_fastest_scenario(self, scenarios: list) -> Dict[str, Any]:
        """Get information about the fastest scenario.
        
        Args:
            scenarios: List of scenario reports
            
        Returns:
            Dictionary with fastest scenario information
        """
        if not scenarios:
            return {"name": None, "duration_ms": 0}
        
        fastest = min(scenarios, key=lambda s: s.total_duration_ms)
        return {
            "name": fastest.scenario_name,
            "duration_ms": fastest.total_duration_ms,
            "duration_seconds": fastest.duration_seconds,
        }
    
    def _get_slowest_scenario(self, scenarios: list) -> Dict[str, Any]:
        """Get information about the slowest scenario.
        
        Args:
            scenarios: List of scenario reports
            
        Returns:
            Dictionary with slowest scenario information
        """
        if not scenarios:
            return {"name": None, "duration_ms": 0}
        
        slowest = max(scenarios, key=lambda s: s.total_duration_ms)
        return {
            "name": slowest.scenario_name,
            "duration_ms": slowest.total_duration_ms,
            "duration_seconds": slowest.duration_seconds,
        }
    
    def _write_to_file(self, data: Dict[str, Any], output_path: Union[str, Path]) -> None:
        """Write data to JSON file.
        
        Args:
            data: Data to write
            output_path: Path to write to
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=self.indent, ensure_ascii=False, default=str)
    
    def to_json_string(self, report: Union[ScenarioReport, TestSuiteReport]) -> str:
        """Convert report to JSON string.
        
        Args:
            report: Report to convert
            
        Returns:
            JSON string representation
        """
        if isinstance(report, ScenarioReport):
            data = self._serialize_scenario_report(report)
        elif isinstance(report, TestSuiteReport):
            data = self._serialize_test_suite_report(report)
        else:
            raise ValueError(f"Unsupported report type: {type(report)}")
        
        return json.dumps(data, indent=self.indent, ensure_ascii=False, default=str) 