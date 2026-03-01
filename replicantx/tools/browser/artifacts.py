# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Artifact management for ReplicantX browser mode (traces, screenshots).
"""

import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime
from playwright.async_api import Page, BrowserContext

from replicantx.models import TraceMode


class ArtifactManager:
    """
    Manages Playwright artifacts (traces and screenshots).
    """

    def __init__(
        self,
        artifacts_dir: str = "artifacts",
        scenario_name: str = "scenario",
        trace_mode: TraceMode = TraceMode.RETAIN_ON_FAILURE,
    ):
        """
        Initialize the artifact manager.

        Args:
            artifacts_dir: Directory to store artifacts
            scenario_name: Name of the scenario (for subdirectories)
            trace_mode: When to retain traces
        """
        self.artifacts_dir = Path(artifacts_dir)
        self.scenario_name = scenario_name
        self.trace_mode = trace_mode
        self.scenario_dir = self.artifacts_dir / scenario_name
        self.trace_path = self.scenario_dir / "trace.zip"
        self.screenshot_dir = self.scenario_dir / "screenshots"
        self.failed = False

        # Create directories
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._tracing_started = False

    async def start_tracing(self, context: BrowserContext):
        """
        Start Playwright tracing for the context.

        Args:
            context: Playwright browser context
        """
        if self.trace_mode == TraceMode.OFF:
            return

        try:
            # Start tracing with screenshots, snapshots, and sources
            await context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True
            )
            self._tracing_started = True
        except Exception as e:
            print(f"⚠️  Failed to start tracing: {e}")

    async def stop_tracing(self, context: BrowserContext, retain: Optional[bool] = None):
        """
        Stop Playwright tracing and save if needed.

        Args:
            context: Playwright browser context
            retain: Whether to retain the trace (overrides trace_mode)
        """
        if not self._tracing_started:
            return

        try:
            # Determine if we should retain the trace
            if retain is None:
                # Use trace_mode to decide
                if self.trace_mode == TraceMode.ON:
                    retain = True
                elif self.trace_mode == TraceMode.RETAIN_ON_FAILURE:
                    retain = self.failed
                else:  # OFF
                    retain = False

            if retain:
                # Stop and save trace
                await context.tracing.stop(path=str(self.trace_path))
                print(f"📦 Trace saved to: {self.trace_path}")
            else:
                # Stop without saving
                await context.tracing.stop()
        except Exception as e:
            print(f"⚠️  Failed to stop tracing: {e}")

        self._tracing_started = False

    async def capture_screenshot(
        self,
        page: Page,
        name: Optional[str] = None,
        force: bool = False,
    ) -> Optional[str]:
        """
        Capture a screenshot of the current page.

        Args:
            page: Playwright page object
            name: Optional name for the screenshot (default: timestamp)
            force: Whether to capture even if not configured

        Returns:
            Path to the screenshot file, or None if not captured
        """
        if not force and self.trace_mode == TraceMode.OFF:
            # Only capture on failure or if forced
            return None

        try:
            # Generate filename
            if name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                name = f"screenshot_{timestamp}"

            screenshot_path = self.screenshot_dir / f"{name}.png"

            # Capture screenshot
            await page.screenshot(path=str(screenshot_path), full_page=True)

            return str(screenshot_path)
        except Exception as e:
            print(f"⚠️  Failed to capture screenshot: {e}")
            return None

    async def capture_failure_screenshot(self, page: Page, step_index: int) -> Optional[str]:
        """
        Capture a screenshot on failure.

        Args:
            page: Playwright page object
            step_index: Step number for filename

        Returns:
            Path to the screenshot file, or None if capture failed
        """
        self.failed = True
        return await self.capture_screenshot(page, name=f"failure_step_{step_index}", force=True)

    def get_artifact_summary(self) -> dict:
        """
        Get a summary of artifacts generated.

        Returns:
            Dictionary with artifact paths
        """
        summary = {
            "scenario_dir": str(self.scenario_dir),
        }

        # Check if trace exists
        if self.trace_path.exists():
            summary["trace"] = str(self.trace_path)

        # List screenshots
        screenshots = list(self.screenshot_dir.glob("*.png"))
        if screenshots:
            summary["screenshots"] = [str(s) for s in sorted(screenshots)]

        return summary

    def mark_failed(self):
        """Mark the scenario as failed (for trace retention)."""
        self.failed = True
