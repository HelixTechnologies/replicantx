# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Playwright browser automation driver for ReplicantX browser mode.
"""

from typing import Optional, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from replicantx.models import BrowserConfig, BrowserObservation
from replicantx.tools.browser.observation import extract_observation
from replicantx.tools.browser.actions import execute_action
from replicantx.tools.browser.artifacts import ArtifactManager


class BrowserAutomationDriver:
    """
    Driver for Playwright browser automation.

    Responsible for launching the browser, navigation, executing actions,
    and producing artifacts.
    """

    def __init__(
        self,
        config: BrowserConfig,
        artifact_manager: ArtifactManager,
        debug: bool = False,
    ):
        """
        Initialize the browser automation driver.

        Args:
            config: Browser configuration
            artifact_manager: Artifact manager for traces/screenshots
            debug: Whether to print debug information
        """
        self.config = config
        self.artifact_manager = artifact_manager
        self.debug = debug

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self):
        """Start the browser and create a new page."""
        if self.debug:
            print(f"🌐 Starting browser: {self.config.browser_type}")

        self.playwright = await async_playwright().start()

        # Launch browser
        browser_launch = getattr(self.playwright, self.config.browser_type)
        self.browser = await browser_launch.launch(
            headless=self.config.headless,
        )

        # Create context with viewport (optional Cloudflare / preview bypass headers, etc.)
        viewport = {
            "width": self.config.viewport.width,
            "height": self.config.viewport.height,
        }
        if self.config.extra_headers:
            self.context = await self.browser.new_context(
                viewport=viewport,
                extra_http_headers=self.config.extra_headers,
            )
        else:
            self.context = await self.browser.new_context(viewport=viewport)

        # Start tracing if configured
        await self.artifact_manager.start_tracing(self.context)

        # Create page
        self.page = await self.context.new_page()

        # Set default timeouts
        self.page.set_default_timeout(self.config.action_timeout_seconds * 1000)
        self.page.set_default_navigation_timeout(self.config.navigation_timeout_seconds * 1000)

        if self.debug:
            print(f"✅ Browser started (headless={self.config.headless})")

    async def stop(self):
        """Stop the browser and cleanup resources."""
        if self.debug:
            print("🛑 Stopping browser")

        # Stop tracing
        if self.context:
            await self.artifact_manager.stop_tracing(self.context)

        # Close page
        if self.page:
            await self.page.close()
            self.page = None

        # Close context
        if self.context:
            await self.context.close()
            self.context = None

        # Close browser
        if self.browser:
            await self.browser.close()
            self.browser = None

        # Stop playwright
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        if self.debug:
            print("✅ Browser stopped")

    async def goto(self, url: str) -> BrowserObservation:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to

        Returns:
            BrowserObservation of the page after navigation
        """
        if self.debug:
            print(f"🔗 Navigating to: {url}")

        await self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout_seconds * 1000,
        )

        # Wait for page to settle
        await self.page.wait_for_load_state("networkidle", timeout=5000)

        # Extract observation
        observation = await extract_observation(
            self.page,
            max_interactive_elements=self.config.max_interactive_elements,
            max_visible_text_chars=self.config.max_visible_text_chars,
        )

        if self.debug:
            print(f"✅ Navigated to: {observation.url}")
            print(f"   Title: {observation.title}")

        return observation

    async def perform(self, action, current_observation: Optional[BrowserObservation] = None):
        """
        Perform a browser action.

        Args:
            action: BrowserAction to perform
            current_observation: Current page observation

        Returns:
            BrowserActionResult
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        # Execute the action
        result = await execute_action(
            self.page,
            action,
            action_timeout_seconds=self.config.action_timeout_seconds,
            observation=current_observation,
            debug=self.debug,
        )

        # Capture screenshot if configured
        if self.config.screenshot_on_each_turn and result.success:
            screenshot_path = await self.artifact_manager.capture_screenshot(
                self.page, force=True
            )
            if screenshot_path:
                result.screenshot_path = screenshot_path

        if self.debug:
            status = "✅" if result.success else "❌"
            print(f"{status} Action: {result.message}")

        return result

    async def capture_observation(self) -> BrowserObservation:
        """
        Capture an observation of the current page.

        Returns:
            BrowserObservation
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        return await extract_observation(
            self.page,
            max_interactive_elements=self.config.max_interactive_elements,
            max_visible_text_chars=self.config.max_visible_text_chars,
        )

    async def screenshot(self, path: str):
        """
        Capture a screenshot of the current page.

        Args:
            path: Path to save the screenshot
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        await self.page.screenshot(path=path, full_page=True)

    def get_page(self) -> Optional[Page]:
        """Get the underlying Playwright page object."""
        return self.page

    def get_context(self) -> Optional[BrowserContext]:
        """Get the underlying Playwright browser context object."""
        return self.context
