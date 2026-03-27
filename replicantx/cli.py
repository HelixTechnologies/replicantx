# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).

"""
Command-line interface for ReplicantX.

This module provides a Typer-based CLI for running test scenarios,
generating reports, and managing test execution in CI/CD environments.
"""

import asyncio
import glob
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env file from current directory or parent directories
    load_dotenv(verbose=False)
except ImportError:
    # dotenv is optional, continue without it
    pass

from . import __version__
from .issue_reporting import IssueProcessingConfig, IssueProcessor
from .models import (
    InteractionMode,
    IssueArtifactUploadMode,
    IssueMode,
    ScenarioConfig,
    TestLevel,
    TestSuiteReport,
)
from .scenarios import BasicScenarioRunner, AgentScenarioRunner, BrowserScenarioRunner
from .reporters import MarkdownReporter, JSONReporter

app = typer.Typer(
    name="replicantx",
    help="End-to-end testing harness for AI agents via web service APIs",
    add_completion=False,
)

console = Console()


def version_callback(value: bool):
    """Show version information."""
    if value:
        console.print(f"ReplicantX version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=version_callback, help="Show version and exit"
    ),
):
    """ReplicantX - End-to-end testing harness for AI agents."""
    pass


@app.command()
def run(
    test_patterns: List[str] = typer.Argument(
        ..., help="Test file patterns (e.g., 'tests/*.yaml', 'tests/specific.yaml')"
    ),
    report: Optional[str] = typer.Option(
        None, "--report", "-r", help="Output report file path (supports .md and .json)"
    ),
    ci: bool = typer.Option(
        False, "--ci", help="CI mode: exit with non-zero code if any tests fail"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Enable verbose output"
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Enable debug mode: Shows detailed technical information including HTTP client setup, request payloads, response validation, AI processing, and assertion results. Perfect for troubleshooting failed tests and performance analysis."
    ),
    llm_debug: bool = typer.Option(
        False, "--llm-debug", help="Enable LLM debug mode: Prints the complete system prompt and user message sent to the LLM on every turn (both API agent and browser planner). Use this to inspect exactly what instructions and context are supplied to the model each step."
    ),
    watch: bool = typer.Option(
        False, "--watch", help="Enable watch mode: Real-time conversation monitoring with live timestamps, user/assistant messages, step results, and final summaries. Perfect for demos, monitoring long tests, and validating conversation flow."
    ),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", "-t", help="Override default timeout in seconds"
    ),
    max_retries: Optional[int] = typer.Option(
        None, "--max-retries", help="Override default max retries"
    ),
    parallel: bool = typer.Option(
        False, "--parallel", help="Run scenarios in parallel (overrides individual scenario settings)"
    ),
    max_concurrent: Optional[int] = typer.Option(
        None, "--max-concurrent", help="Maximum number of scenarios to run concurrently (default: unlimited)"
    ),
    issue_mode: IssueMode = typer.Option(
        IssueMode.OFF,
        "--issue-mode",
        help="Browser issue handling mode: off, auto-high-confidence, or draft-only",
    ),
    issue_repo: str = typer.Option(
        "HelixTechnologies/helix-agent",
        "--issue-repo",
        help="GitHub repository to file issues against, in owner/name format",
    ),
    issue_artifact_upload: IssueArtifactUploadMode = typer.Option(
        IssueArtifactUploadMode.ON,
        "--issue-artifact-upload",
        help="Whether to upload issue artifacts when issue processing is enabled",
    ),
    issue_output: str = typer.Option(
        "artifacts/issues",
        "--issue-output",
        help="Directory to write issue bundles and markdown drafts",
    ),
    logfire_config: Optional[str] = typer.Option(
        None,
        "--logfire-config",
        help="Optional path to a Logfire query YAML config. Defaults to replicantx.logfire.yaml if present.",
    ),
):
    """Run test scenarios from YAML files.

MONITORING & DEBUGGING:
  --debug: Technical deep-dive with HTTP requests, AI model details, and validation results
  --llm-debug: Prints complete system prompt + user message for every LLM call each turn
  --watch: Real-time conversation monitoring with timestamps and live updates  
  --debug --watch: Combined mode for comprehensive analysis during development

EXAMPLES:
  replicantx run tests/*.yaml --report report.md
  replicantx run tests/agent_test.yaml --watch --debug
  replicantx run tests/*.yaml --ci --report results.json
  replicantx run tests/*.yaml --parallel --max-concurrent 3
  replicantx run tests/browser_test.yaml --issue-mode draft-only --issue-artifact-upload off
  replicantx run tests/browser_test.yaml --issue-mode auto-high-confidence --issue-repo HelixTechnologies/helix-agent
  replicantx run tests/browser_test.yaml --issue-mode draft-only --logfire-config replicantx.logfire.yaml
    """
    console.print(f"🚀 ReplicantX {__version__} - Starting test execution")
    
    # Find all test files
    test_files = []
    for pattern in test_patterns:
        matching_files = glob.glob(pattern)
        if not matching_files:
            console.print(f"❌ No files found matching pattern: {pattern}")
            if ci:
                raise typer.Exit(1)
            continue
        test_files.extend(matching_files)
    
    if not test_files:
        console.print("❌ No test files found")
        if ci:
            raise typer.Exit(1)
        return
    
    console.print(f"📋 Found {len(test_files)} test file(s)")
    
    if verbose:
        for file in test_files:
            console.print(f"  - {file}")
    
    # Load and run scenarios
    asyncio.run(run_scenarios_async(
        test_files=test_files,
        report_path=report,
        ci_mode=ci,
        verbose=verbose,
        debug=debug,
        llm_debug=llm_debug,
        watch=watch,
        timeout_override=timeout,
        max_retries_override=max_retries,
        parallel=parallel,
        max_concurrent=max_concurrent,
        issue_mode=issue_mode,
        issue_repo=issue_repo,
        issue_artifact_upload=issue_artifact_upload,
        issue_output=issue_output,
        logfire_config=logfire_config,
    ))


async def run_scenarios_async(
    test_files: List[str],
    report_path: Optional[str] = None,
    ci_mode: bool = False,
    verbose: bool = False,
    debug: bool = False,
    llm_debug: bool = False,
    watch: bool = False,
    timeout_override: Optional[int] = None,
    max_retries_override: Optional[int] = None,
    parallel: bool = False,
    max_concurrent: Optional[int] = None,
    issue_mode: IssueMode = IssueMode.OFF,
    issue_repo: str = "HelixTechnologies/helix-agent",
    issue_artifact_upload: IssueArtifactUploadMode = IssueArtifactUploadMode.ON,
    issue_output: str = "artifacts/issues",
    logfire_config: Optional[str] = None,
):
    """Run scenarios asynchronously."""
    # Initialize test suite report
    suite_report = TestSuiteReport(
        total_scenarios=len(test_files),
        passed_scenarios=0,
        failed_scenarios=0,
        scenario_reports=[],
        started_at=datetime.now(),
    )
    
    # Load and validate scenarios
    scenarios = []
    for file_path in test_files:
        try:
            config = load_scenario_config(file_path)
            
            # Apply overrides
            if timeout_override:
                config.timeout_seconds = timeout_override
            if max_retries_override:
                config.max_retries = max_retries_override
            
            scenarios.append((file_path, config))
        except Exception as e:
            console.print(f"❌ Failed to load {file_path}: {e}")
            if ci_mode:
                raise typer.Exit(1)
            continue
    
    if not scenarios:
        console.print("❌ No valid scenarios loaded")
        if ci_mode:
            raise typer.Exit(1)
        return
    
    # Run scenarios
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        # Determine execution mode
        should_run_parallel = parallel or any(config.parallel for _, config in scenarios)
        
        if should_run_parallel:
            console.print(f"🔄 Running scenarios in parallel mode")
            if max_concurrent:
                console.print(f"📊 Max concurrent scenarios: {max_concurrent}")
            await run_scenarios_parallel(
                scenarios=scenarios,
                suite_report=suite_report,
                progress=progress,
                ci_mode=ci_mode,
                verbose=verbose,
                debug=debug,
                llm_debug=llm_debug,
                watch=watch,
                max_concurrent=max_concurrent,
            )
        else:
            console.print(f"🔄 Running scenarios sequentially")
            await run_scenarios_sequential(
                scenarios=scenarios,
                suite_report=suite_report,
                progress=progress,
                ci_mode=ci_mode,
                verbose=verbose,
                debug=debug,
                llm_debug=llm_debug,
                watch=watch,
            )
    
    # Finalize report
    suite_report.completed_at = datetime.now()

    if issue_mode != IssueMode.OFF:
        issue_config = IssueProcessingConfig.from_runtime(
            issue_mode=issue_mode,
            issue_repo=issue_repo,
            artifact_upload_mode=issue_artifact_upload,
            issue_output_dir=issue_output,
            logfire_config_path=logfire_config,
        )
        processor = IssueProcessor(config=issue_config)
        await processor.process_suite(suite_report.scenario_reports)

    # Display summary
    display_summary(suite_report, verbose)
    display_issue_summary(suite_report, issue_mode)
    
    # Generate reports
    if report_path:
        generate_reports(suite_report, report_path)
    
    # Exit with appropriate code in CI mode
    if ci_mode and suite_report.failed_scenarios > 0:
        console.print(f"\n❌ CI mode: {suite_report.failed_scenarios} scenario(s) failed")
        raise typer.Exit(1)
    
    console.print(f"\n✅ Test execution completed successfully")


async def run_scenarios_sequential(
    scenarios: List[tuple],
    suite_report: TestSuiteReport,
    progress: Progress,
    ci_mode: bool,
    verbose: bool,
    debug: bool,
    llm_debug: bool = False,
    watch: bool = False,
):
    """Run scenarios sequentially."""
    for file_path, config in scenarios:
        task = progress.add_task(f"Running {Path(file_path).name}...", total=None)

        try:
            # Create appropriate runner based on level and interaction mode
            if config.level == TestLevel.BASIC:
                runner = BasicScenarioRunner(config, debug=debug, watch=watch)
            elif config.level == TestLevel.AGENT:
                # Check if browser mode
                if config.replicant and config.replicant.interaction_mode == InteractionMode.BROWSER:
                    # Import auth providers
                    from .auth import create_auth_provider
                    auth_provider = create_auth_provider(config.auth)
                    runner = BrowserScenarioRunner(config, auth_provider, debug=debug, watch=watch, verbose=verbose, llm_debug=llm_debug)
                else:
                    runner = AgentScenarioRunner(config, debug=debug, watch=watch, verbose=verbose, llm_debug=llm_debug)
            else:
                raise ValueError(f"Unsupported test level: {config.level}")

            # Run the scenario
            scenario_report = await runner.run()
            scenario_report.source_file = file_path
            suite_report.scenario_reports.append(scenario_report)

            # Update counters
            if scenario_report.passed:
                suite_report.passed_scenarios += 1
                progress.update(task, description=f"✅ {Path(file_path).name}")
            else:
                suite_report.failed_scenarios += 1
                progress.update(task, description=f"❌ {Path(file_path).name}")

            if verbose:
                console.print(f"  Steps: {scenario_report.passed_steps}/{scenario_report.total_steps}")
                console.print(f"  Duration: {scenario_report.duration_seconds:.2f}s")
                if scenario_report.error:
                    console.print(f"  Error: {scenario_report.error}")

        except Exception as e:
            console.print(f"❌ Error running {file_path}: {e}")
            suite_report.failed_scenarios += 1
            progress.update(task, description=f"❌ {Path(file_path).name} (error)")

            if ci_mode:
                raise typer.Exit(1)

        progress.remove_task(task)


async def run_scenarios_parallel(
    scenarios: List[tuple],
    suite_report: TestSuiteReport,
    progress: Progress,
    ci_mode: bool,
    verbose: bool,
    debug: bool,
    llm_debug: bool = False,
    watch: bool = False,
    max_concurrent: Optional[int] = None,
):
    """Run scenarios in parallel."""
    import asyncio
    from asyncio import Semaphore
    
    # Create semaphore for concurrency control
    semaphore = Semaphore(max_concurrent) if max_concurrent else None
    
    async def run_single_scenario(file_path: str, config: ScenarioConfig):
        """Run a single scenario with proper error handling."""
        task_id = None
        try:
            # Add progress task
            task_id = progress.add_task(f"Running {Path(file_path).name}...", total=None)
            
            # Apply semaphore if concurrency is limited
            if semaphore:
                async with semaphore:
                    return await _execute_scenario(file_path, config, task_id, debug, watch, verbose, llm_debug)
            else:
                return await _execute_scenario(file_path, config, task_id, debug, watch, verbose, llm_debug)
                
        except Exception as e:
            console.print(f"❌ Error running {file_path}: {e}")
            if task_id:
                progress.update(task_id, description=f"❌ {Path(file_path).name} (error)")
            return {
                'file_path': file_path,
                'config': config,
                'report': None,
                'error': str(e),
                'task_id': task_id
            }
    
    # Create all scenario tasks
    tasks = [run_single_scenario(file_path, config) for file_path, config in scenarios]
    
    # Run all scenarios concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    for result in results:
        if isinstance(result, Exception):
            console.print(f"❌ Unexpected error: {result}")
            suite_report.failed_scenarios += 1
            continue
            
        file_path = result['file_path']
        config = result['config']
        scenario_report = result['report']
        error = result.get('error')
        task_id = result['task_id']
        
        if error:
            suite_report.failed_scenarios += 1
            if ci_mode:
                raise typer.Exit(1)
        elif scenario_report:
            suite_report.scenario_reports.append(scenario_report)
            
            # Update counters
            if scenario_report.passed:
                suite_report.passed_scenarios += 1
                progress.update(task_id, description=f"✅ {Path(file_path).name}")
            else:
                suite_report.failed_scenarios += 1
                progress.update(task_id, description=f"❌ {Path(file_path).name}")
            
            if verbose:
                console.print(f"  Steps: {scenario_report.passed_steps}/{scenario_report.total_steps}")
                console.print(f"  Duration: {scenario_report.duration_seconds:.2f}s")
                if scenario_report.error:
                    console.print(f"  Error: {scenario_report.error}")
        
        # Remove progress task
        if task_id:
            progress.remove_task(task_id)


async def _execute_scenario(
    file_path: str,
    config: ScenarioConfig,
    task_id: int,
    debug: bool,
    watch: bool,
    verbose: bool,
    llm_debug: bool = False,
):
    """Execute a single scenario and return the result."""
    # Create appropriate runner based on level and interaction mode
    if config.level == TestLevel.BASIC:
        runner = BasicScenarioRunner(config, debug=debug, watch=watch)
    elif config.level == TestLevel.AGENT:
        # Check if browser mode
        if config.replicant and config.replicant.interaction_mode == InteractionMode.BROWSER:
            # Import auth providers
            from .auth import create_auth_provider
            auth_provider = create_auth_provider(config.auth)
            runner = BrowserScenarioRunner(config, auth_provider, debug=debug, watch=watch, verbose=verbose, llm_debug=llm_debug)
        else:
            runner = AgentScenarioRunner(config, debug=debug, watch=watch, verbose=verbose, llm_debug=llm_debug)
    else:
        raise ValueError(f"Unsupported test level: {config.level}")

    # Run the scenario
    scenario_report = await runner.run()
    scenario_report.source_file = file_path

    return {
        'file_path': file_path,
        'config': config,
        'report': scenario_report,
        'error': None,
        'task_id': task_id
    }


def substitute_env_vars(value):
    """Recursively substitute environment variables in YAML data.
    
    Args:
        value: Value to process (string, dict, list, or other)
        
    Returns:
        Value with environment variables substituted
    """
    import os
    import re
    
    if isinstance(value, str):
        # Simple template substitution for {{ env.VAR_NAME }}
        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                raise ValueError(f"Environment variable {var_name} not found")
            return env_value
        
        return re.sub(r'\{\{\s*env\.([A-Z_]+)\s*\}\}', replace_env_var, value)
    
    elif isinstance(value, dict):
        # Recursively process dictionary
        return {k: substitute_env_vars(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        # Recursively process list
        return [substitute_env_vars(item) for item in value]
    
    else:
        # Return other types unchanged
        return value


def load_scenario_config(file_path: str) -> ScenarioConfig:
    """Load scenario configuration from YAML file.
    
    Args:
        file_path: Path to YAML file
        
    Returns:
        Loaded scenario configuration
        
    Raises:
        Exception: If file cannot be loaded or parsed
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Validate required fields
        if not isinstance(data, dict):
            raise ValueError("YAML file must contain a dictionary")
        
        # Substitute environment variables
        data = substitute_env_vars(data)
        
        # Convert to ScenarioConfig
        config = ScenarioConfig(**data)
        return config
        
    except FileNotFoundError:
        raise Exception(f"File not found: {file_path}")
    except yaml.YAMLError as e:
        raise Exception(f"Invalid YAML: {e}")
    except Exception as e:
        raise Exception(f"Invalid scenario configuration: {e}")


def display_summary(suite_report: TestSuiteReport, verbose: bool = False):
    """Display test execution summary.
    
    Args:
        suite_report: Test suite report to display
    """
    console.print("\n📊 Test Execution Summary")
    console.print("=" * 50)
    
    # Overall status
    if suite_report.passed_scenarios == suite_report.total_scenarios:
        console.print("✅ All scenarios passed!", style="bold green")
    else:
        console.print(f"❌ {suite_report.failed_scenarios} scenario(s) failed", style="bold red")
    
    # Create summary table
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Metric")
    table.add_column("Value")
    
    table.add_row("Total Scenarios", str(suite_report.total_scenarios))
    table.add_row("Passed", str(suite_report.passed_scenarios))
    table.add_row("Failed", str(suite_report.failed_scenarios))
    table.add_row("Success Rate", f"{suite_report.success_rate:.1f}%")
    table.add_row("Total Duration", f"{suite_report.duration_seconds:.2f}s")
    
    console.print(table)
    
    # Scenario details
    if suite_report.scenario_reports:
            console.print("\n📋 Scenario Details")
            
            scenario_table = Table(show_header=True, header_style="bold blue")
            scenario_table.add_column("Scenario")
            scenario_table.add_column("Status")
            scenario_table.add_column("Steps")
            scenario_table.add_column("Duration")
            scenario_table.add_column("Justification")
            
            for scenario in suite_report.scenario_reports:
                status = "✅ PASS" if scenario.passed else "❌ FAIL"
                steps = f"{scenario.passed_steps}/{scenario.total_steps}"
                duration = f"{scenario.duration_seconds:.2f}s"
                justification = scenario.justification or "No justification available"
                
                # Truncate justification for table display
                if len(justification) > 80:
                    justification = justification[:77] + "..."
                
                scenario_table.add_row(
                    scenario.scenario_name,
                    status,
                    steps,
                    duration,
                    justification
                )
            
            console.print(scenario_table)
            
            # Show detailed justification for failed scenarios
            failed_scenarios = [s for s in suite_report.scenario_reports if not s.passed]
            if failed_scenarios and verbose:
                console.print("\n🔍 Detailed Justification for Failed Scenarios")
                for scenario in failed_scenarios:
                    console.print(f"\n**{scenario.scenario_name}**")
                    if scenario.justification:
                        console.print(f"💭 {scenario.justification}")
                    if scenario.error:
                        console.print(f"❌ Error: {scenario.error}")


def display_issue_summary(
    suite_report: TestSuiteReport,
    issue_mode: IssueMode,
) -> None:
    """Display issue processing results when enabled."""
    if issue_mode == IssueMode.OFF:
        return

    processed = [
        scenario
        for scenario in suite_report.scenario_reports
        if scenario.issue_classification is not None
    ]
    if not processed:
        console.print("\n🪲 Issue Processing")
        console.print("No browser scenarios produced issue bundles.")
        return

    console.print("\n🪲 Issue Processing")
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Scenario")
    table.add_column("Decision")
    table.add_column("Bundle")
    table.add_column("Issue")

    for scenario in processed:
        decision = scenario.issue_classification.decision.value
        bundle = scenario.issue_bundle_path or "n/a"
        issue = scenario.issue_url or (
            "draft only"
            if scenario.issue_classification.decision.value == "auto_file"
            and issue_mode == IssueMode.DRAFT_ONLY
            else "not filed"
        )
        table.add_row(
            scenario.scenario_name,
            decision,
            bundle,
            issue,
        )

    console.print(table)


def generate_reports(suite_report: TestSuiteReport, report_path: str):
    """Generate reports in the specified format.
    
    Args:
        suite_report: Test suite report
        report_path: Path to write report file
    """
    console.print(f"\n📝 Generating report: {report_path}")
    
    path = Path(report_path)
    
    try:
        if path.suffix.lower() == '.md':
            reporter = MarkdownReporter()
            reporter.write_test_suite_report(suite_report, path)
        elif path.suffix.lower() == '.json':
            reporter = JSONReporter()
            reporter.write_test_suite_report(suite_report, path)
        else:
            # Default to markdown
            reporter = MarkdownReporter()
            reporter.write_test_suite_report(suite_report, path)
            console.print("ℹ️  No file extension specified, defaulting to Markdown format")
        
        console.print(f"✅ Report generated: {path}")
        
    except Exception as e:
        console.print(f"❌ Failed to generate report: {e}")


@app.command()
def validate(
    test_patterns: List[str] = typer.Argument(
        ..., help="Test file patterns to validate"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
):
    """Validate test scenario YAML files without running them."""
    console.print("🔍 Validating test scenarios...")
    
    # Find all test files
    test_files = []
    for pattern in test_patterns:
        matching_files = glob.glob(pattern)
        if not matching_files:
            console.print(f"❌ No files found matching pattern: {pattern}")
            continue
        test_files.extend(matching_files)
    
    if not test_files:
        console.print("❌ No test files found")
        raise typer.Exit(1)
    
    console.print(f"📋 Found {len(test_files)} test file(s)")
    
    # Validate each file
    valid_files = 0
    invalid_files = 0
    
    for file_path in test_files:
        try:
            config = load_scenario_config(file_path)
            console.print(f"✅ {file_path}")
            valid_files += 1
            
            if verbose:
                console.print(f"  - Name: {config.name}")
                console.print(f"  - Level: {config.level.value}")
                if config.level == TestLevel.BASIC and config.steps:
                    console.print(f"  - Steps: {len(config.steps)}")
                elif config.level == TestLevel.AGENT and config.replicant:
                    console.print(f"  - Goal: {config.replicant.goal}")
                    console.print(f"  - Facts: {len(config.replicant.facts)} items")
                console.print(f"  - Auth: {config.auth.provider.value}")
                
        except Exception as e:
            console.print(f"❌ {file_path}: {e}")
            invalid_files += 1
    
    # Summary
    console.print(f"\n📊 Validation Results")
    console.print(f"Valid files: {valid_files}")
    console.print(f"Invalid files: {invalid_files}")
    
    if invalid_files > 0:
        raise typer.Exit(1)
    
    console.print("✅ All test files are valid!")


if __name__ == "__main__":
    app() 
