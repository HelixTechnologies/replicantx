# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser action execution for ReplicantX browser mode.
"""

import asyncio
import time
from typing import Optional, Dict, Any
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from replicantx.models import BrowserAction, BrowserActionResult, BrowserObservation
from replicantx.tools.browser.observation import extract_observation


async def execute_action(
    page: Page,
    action: BrowserAction,
    action_timeout_seconds: int = 15,
    observation: Optional[BrowserObservation] = None,
    debug: bool = False,
) -> BrowserActionResult:
    """
    Execute a browser action on the page.

    Args:
        page: Playwright page object
        action: Action to execute
        action_timeout_seconds: Timeout for action execution
        observation: Current page observation (for element locators)
        debug: Whether to print debug information

    Returns:
        BrowserActionResult: Result of the action
    """
    start_time = time.time()
    success = False
    message = ""
    error = None
    new_observation = None

    try:
        if debug:
            print(f"🔍 Executing action: {action.action_type}")

        if action.action_type == "send_chat":
            success, message, new_observation = await _execute_send_chat(
                page, action.value, action_timeout_seconds
            )
        elif action.action_type == "click":
            success, message, new_observation = await _execute_click(
                page, action.target, observation, action_timeout_seconds
            )
        elif action.action_type == "fill":
            success, message, new_observation = await _execute_fill(
                page, action.target, action.value, action_timeout_seconds
            )
        elif action.action_type == "press":
            success, message, new_observation = await _execute_press(
                page, action.value, action_timeout_seconds
            )
        elif action.action_type == "wait":
            success, message, new_observation = await _execute_wait(
                page, action.duration_ms
            )
        elif action.action_type == "wait_for_text":
            success, message, new_observation = await _execute_wait_for_text(
                page, action.value, action_timeout_seconds
            )
        elif action.action_type == "scroll":
            success, message, new_observation = await _execute_scroll(
                page, action.direction, action.amount
            )
        elif action.action_type == "navigate":
            success, message, new_observation = await _execute_navigate(
                page, action.url, action_timeout_seconds
            )
        else:
            success = False
            message = f"Unknown action type: {action.action_type}"

    except Exception as e:
        success = False
        message = f"Action failed with exception: {str(e)}"
        error = str(e)

    latency_ms = (time.time() - start_time) * 1000

    return BrowserActionResult(
        action=action,
        success=success,
        message=message,
        observation=new_observation,
        screenshot_path=None,  # Will be set by artifact manager
        error=error,
        latency_ms=latency_ms,
    )


async def _execute_send_chat(
    page: Page, message: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a send chat action.

    Detects chat input using heuristics, types the message, and presses Enter.

    Args:
        page: Playwright page object
        message: Message to send
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    from replicantx.tools.browser.observation import detect_chat_input

    # Try to find chat input
    chat_input_selector = await detect_chat_input(page)

    if not chat_input_selector:
        # Fallback: try to find any visible textarea or input
        try:
            textarea = await page.wait_for_selector("textarea, input[type='text']", timeout=5000)
            if textarea:
                chat_input_selector = "textarea, input[type='text']"
        except Exception:
            pass

    if not chat_input_selector:
        return False, "Could not find chat input field", None

    try:
        # Type the message
        await page.fill(chat_input_selector, message, timeout=timeout_seconds * 1000)

        # Press Enter to send
        await page.press(chat_input_selector, "Enter")

        # Wait for response (network idle or debounce)
        await _wait_for_page_settle(page, timeout_seconds)

        # Extract new observation
        new_observation = await extract_observation(page)

        return True, f"Sent chat message: {message}", new_observation
    except Exception as e:
        return False, f"Failed to send chat: {str(e)}", None


async def _execute_click(
    page: Page,
    element_id: str,
    observation: Optional[BrowserObservation],
    timeout_seconds: int,
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a click action using the stored element reference.

    Args:
        page: Playwright page object
        element_id: Index into window.__rx_elements
        observation: Current page observation
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    target_name = element_id
    if observation:
        for elem in observation.interactive_elements:
            if elem.id == element_id:
                target_name = f"{elem.role}: {elem.name}"
                break

    try:
        handle = await page.evaluate_handle(
            f"window.__rx_elements && window.__rx_elements[{element_id}]"
        )
        is_valid = await page.evaluate("el => el instanceof HTMLElement", handle)
        if not is_valid:
            return False, f"Element {element_id} no longer exists in the DOM", None

        await handle.as_element().click(timeout=timeout_seconds * 1000)
        await _wait_for_page_settle(page, timeout_seconds)
        new_observation = await extract_observation(page)
        return True, f"Clicked {target_name}", new_observation
    except Exception as e:
        return False, f"Failed to click element {element_id}: {str(e)}", None


async def _execute_fill(
    page: Page,
    element_id: str,
    value: str,
    timeout_seconds: int,
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a fill action using the stored element reference.

    Args:
        page: Playwright page object
        element_id: Index into window.__rx_elements
        value: Value to type
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    if not value:
        return False, "No value provided for fill action", None

    try:
        handle = await page.evaluate_handle(
            f"window.__rx_elements && window.__rx_elements[{element_id}]"
        )
        is_valid = await page.evaluate("el => el instanceof HTMLElement", handle)
        if not is_valid:
            return False, f"Element {element_id} no longer exists in the DOM", None

        element = handle.as_element()

        # Step 1: Try plain fill first
        try:
            await element.click(timeout=timeout_seconds * 1000)
            await element.fill(value, timeout=timeout_seconds * 1000)
        except Exception:
            # fill() fails on non-input elements (custom selects, divs, etc.)
            # Fall through to the type-and-select approach below
            await element.click(timeout=timeout_seconds * 1000)
            await page.keyboard.type(value, delay=30)

        # Step 2: Wait briefly for any dropdown/combobox options to appear
        await asyncio.sleep(0.4)

        # Step 3: Look for dropdown options that match the typed value
        selected = await _try_select_dropdown_option(page, value)

        if selected:
            await asyncio.sleep(0.3)
            new_observation = await extract_observation(page)
            return True, f"Selected \"{value}\" from dropdown for element {element_id}", new_observation

        new_observation = await extract_observation(page)
        return True, f"Filled element {element_id} with: {value}", new_observation
    except Exception as e:
        return False, f"Failed to fill element {element_id}: {str(e)}", None


async def _try_select_dropdown_option(page: Page, value: str) -> bool:
    """
    After typing into a combobox/select, look for a visible dropdown
    option that matches the value and click it.

    Handles common patterns: listbox roles, data-option attributes,
    li items inside dropdown containers, etc.

    Returns True if an option was found and clicked.
    """
    value_lower = value.lower().strip()

    # Common selectors for dropdown options (ordered by specificity)
    option_selectors = [
        "[role='option']",
        "[role='listbox'] li",
        "[role='listbox'] [role='option']",
        "ul[class*='menu'] li",
        "ul[class*='list'] li",
        "div[class*='option']",
        "div[class*='menu'] div[class*='option']",
        ".rc-virtual-list .ant-select-item",
        "li[data-option]",
    ]

    for selector in option_selectors:
        try:
            options = await page.query_selector_all(selector)
            for opt in options:
                if not await opt.is_visible():
                    continue
                text = (await opt.inner_text()).strip()
                if not text:
                    continue
                # Case-insensitive containment match in either direction
                if value_lower in text.lower() or text.lower() in value_lower:
                    await opt.click()
                    return True
        except Exception:
            continue

    return False


async def _execute_press(
    page: Page, key: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a press key action.

    Args:
        page: Playwright page object
        key: Key to press (e.g., "Enter", "Escape")
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    try:
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)

        new_observation = await extract_observation(page)

        return True, f"Pressed key: {key}", new_observation
    except Exception as e:
        return False, f"Failed to press key: {str(e)}", None


async def _execute_wait(
    page: Page, duration_ms: Optional[int]
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a wait action.

    Args:
        page: Playwright page object
        duration_ms: Duration to wait in milliseconds

    Returns:
        Tuple of (success, message, new_observation)
    """
    if duration_ms is None:
        duration_ms = 2000
    duration_ms = min(duration_ms, 10000)

    await asyncio.sleep(duration_ms / 1000.0)

    new_observation = await extract_observation(page)

    return True, f"Waited {duration_ms}ms", new_observation


async def _execute_wait_for_text(
    page: Page, text: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Wait for text to appear on the page.

    Args:
        page: Playwright page object
        text: Text to wait for
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    try:
        await page.wait_for_selector(
            f":has-text('{text}')", timeout=timeout_seconds * 1000
        )

        new_observation = await extract_observation(page)

        return True, f"Found text: {text}", new_observation
    except Exception as e:
        return False, f"Text not found: {text}", None


async def _execute_scroll(
    page: Page, direction: Optional[str], amount: Optional[int]
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a scroll action.

    Args:
        page: Playwright page object
        direction: Direction to scroll (up or down)
        amount: Amount to scroll in pixels

    Returns:
        Tuple of (success, message, new_observation)
    """
    if direction is None:
        direction = "down"
    if amount is None:
        amount = 500

    try:
        if direction == "down":
            await page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await page.evaluate(f"window.scrollBy(0, -{amount})")
        else:
            return False, f"Invalid scroll direction: {direction}", None

        await asyncio.sleep(0.5)

        new_observation = await extract_observation(page)

        return True, f"Scrolled {direction} by {amount}px", new_observation
    except Exception as e:
        return False, f"Failed to scroll: {str(e)}", None


async def _execute_navigate(
    page: Page, url: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Execute a navigate action.

    Args:
        page: Playwright page object
        url: URL to navigate to
        timeout_seconds: Timeout for action

    Returns:
        Tuple of (success, message, new_observation)
    """
    try:
        await page.goto(url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")

        # Wait for page to settle
        await _wait_for_page_settle(page, timeout_seconds)

        new_observation = await extract_observation(page)

        return True, f"Navigated to: {url}", new_observation
    except Exception as e:
        return False, f"Failed to navigate: {str(e)}", None


async def _wait_for_page_settle(page: Page, timeout_seconds: int = 15):
    """
    Wait for the page to settle after an action.

    Tries multiple strategies:
    1. Network idle (if applicable)
    2. Short debounce
    3. Wait for new content

    Args:
        page: Playwright page object
        timeout_seconds: Timeout for waiting
    """
    try:
        # Try network idle first
        await page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000)
    except Exception:
        # Fall back to debounce
        await asyncio.sleep(0.5)
