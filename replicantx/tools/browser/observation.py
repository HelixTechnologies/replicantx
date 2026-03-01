# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser observation extraction for ReplicantX browser mode.
"""

import re
from typing import List, Optional
from datetime import datetime

from playwright.async_api import Page

from replicantx.models import InteractiveElement, BrowserObservation


async def extract_observation(
    page: Page,
    max_interactive_elements: int = 40,
    max_visible_text_chars: int = 6000,
) -> BrowserObservation:
    """
    Extract a compact, LLM-friendly observation from a web page.

    Args:
        page: Playwright page object
        max_interactive_elements: Maximum number of interactive elements to extract
        max_visible_text_chars: Maximum characters of visible text to extract

    Returns:
        BrowserObservation: Compact page observation
    """
    # Get basic page info
    url = page.url
    title = await page.title()

    # Extract visible text
    visible_text = await extract_visible_text(page, max_chars=max_visible_text_chars)

    # Extract interactive elements
    interactive_elements = await extract_interactive_elements(
        page, max_elements=max_interactive_elements
    )

    return BrowserObservation(
        url=url,
        title=title,
        visible_text=visible_text,
        interactive_elements=interactive_elements,
        timestamp=datetime.now(),
    )


async def extract_visible_text(page: Page, max_chars: int = 6000) -> str:
    """
    Extract visible text from the page.

    Uses JavaScript to get visible text, strips repeated whitespace,
    and truncates to max_chars.

    Args:
        page: Playwright page object
        max_chars: Maximum characters to return

    Returns:
        Sanitized visible text
    """
    # Use JavaScript to get visible text (more reliable than innerText)
    text = await page.evaluate(
        """() => {
            // Get body text
            let text = document.body ? document.body.innerText : '';

            // Remove excessive whitespace
            text = text.replace(/\\s+/g, ' ').trim();

            return text;
        }"""
    )

    # Truncate if necessary
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    return text


async def extract_interactive_elements(
    page: Page, max_elements: int = 40
) -> List[InteractiveElement]:
    """
    Extract interactive elements from the page.

    Queries for common interactables, filters for visible/enabled elements
    with meaningful names, and returns a sorted list.

    Args:
        page: Playwright page object
        max_elements: Maximum number of elements to return

    Returns:
        List of interactive elements
    """
    # Use JavaScript to extract interactive elements
    elements_data = await page.evaluate(
        """() => {
            const elements = [];

            // Common interactive selectors
            const selectors = [
                'button:not([disabled])',
                'a[href]',
                'input:not([disabled])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[role="tab"]',
                '[role="checkbox"]',
                '[role="radio"]',
            ];

            const uniqueElements = new Set();

            selectors.forEach(selector => {
                const nodes = document.querySelectorAll(selector);
                nodes.forEach(node => {
                    // Skip if already added
                    if (uniqueElements.has(node)) return;
                    uniqueElements.add(node);

                    // Check visibility
                    const rect = node.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0;

                    if (!isVisible) return;

                    // Get accessible name or text
                    let name = '';

                    // Try aria-label first
                    name = node.getAttribute('aria-label') || '';

                    // Try placeholder for inputs
                    if (!name && (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA')) {
                        name = node.getAttribute('placeholder') || '';
                    }

                    // Try inner text
                    if (!name) {
                        name = node.innerText || node.textContent || '';
                    }

                    // Clean up name
                    name = name.trim().slice(0, 100); // Limit to 100 chars

                    if (!name) return; // Skip elements without meaningful names

                    // Get role
                    let role = node.tagName.toLowerCase();
                    if (node.getAttribute('role')) {
                        role = node.getAttribute('role');
                    }

                    // Store element info
                    elements.push({
                        tagName: node.tagName,
                        role: role,
                        name: name,
                        // We'll use a unique identifier for the locator
                        id: `${elements.length}`,
                    });
                });
            });

            return elements;
        }"""
    )

    # Convert to InteractiveElement objects
    interactive_elements = []
    for elem_data in elements_data[:max_elements]:
        element = InteractiveElement(
            id=elem_data["id"],
            role=elem_data["role"],
            name=elem_data["name"],
            locator=None,  # Will be set by the action handler
        )
        interactive_elements.append(element)

    return interactive_elements


async def detect_chat_input(page: Page) -> Optional[str]:
    """
    Detect chat input field using heuristics.

    Tries common selectors for chat inputs and returns the first match.

    Args:
        page: Playwright page object

    Returns:
        Locator string for the chat input, or None if not found
    """
    # Common chat input selectors (in order of preference)
    selectors = [
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='chat' i]",
        "input[placeholder*='message' i]",
        "input[placeholder*='chat' i]",
        "textarea[placeholder*='type' i]",
        "input[placeholder*='type' i]",
        "[data-testid='chat-input']",
        "[data-testid='message-input']",
        "[name='message']",
        "[name='chat']",
        "div[contenteditable='true']:not([aria-hidden])",
    ]

    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Check if visible
                is_visible = await element.is_visible()
                if is_visible:
                    return selector
        except Exception:
            continue

    return None


async def detect_chat_send_button(page: Page) -> Optional[str]:
    """
    Detect chat send button using heuristics.

    Tries common selectors for send buttons and returns the first match.

    Args:
        page: Playwright page object

    Returns:
        Locator string for the send button, or None if not found
    """
    # Common send button selectors (in order of preference)
    selectors = [
        "button[aria-label*='send' i]",
        "button[aria-label*='submit' i]",
        "[data-testid='chat-send']",
        "[data-testid='send-button']",
        "button[type='submit']",
        "button:has-text('Send')",
        "button:has-text('Submit')",
        "button svg[class*='send']",
    ]

    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Check if visible
                is_visible = await element.is_visible()
                if is_visible:
                    return selector
        except Exception:
            continue

    return None
