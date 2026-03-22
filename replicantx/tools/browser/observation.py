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
    Extract interactive elements from the page with smart ranking.

    Queries for common interactables, filters for visible/enabled elements
    with meaningful names, and returns a sorted list with chat-thread elements
    prioritized.

    Args:
        page: Playwright page object
        max_elements: Maximum number of elements to return

    Returns:
        List of interactive elements, ranked by relevance
    """
    # First, try to detect chat area
    chat_area_selector = await _detect_chat_area(page)

    # Use JavaScript to extract interactive elements, rank them, and store
    # references in window.__rx_elements so actions can target them by index.
    elements_data = await page.evaluate(
        """(chatAreaSelector) => {
            const collected = [];
            window.__rx_elements = [];
            const topLayerSelectors = [
                '[aria-modal="true"]',
                '[role="alertdialog"]',
                '[role="dialog"]',
                '[role="listbox"]',
                '[role="menu"]',
                '[data-radix-popper-content-wrapper]',
                '[data-state="open"]',
                '[class*="modal"]',
                '[class*="dialog"]',
                '[class*="drawer"]',
                '[class*="sheet"]',
                '[class*="popover"]',
            ];
            const topLayerSelector = topLayerSelectors.join(',');

            const selectors = [
                'button:not([disabled])',
                'a[href]',
                'input:not([disabled])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                '[role="combobox"]',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[role="tab"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="option"]',
                '[role="listbox"] > *',
                '[aria-autocomplete]',
                '[contenteditable="true"]',
                'li[data-option]',
                'div[class*="option"]',
            ];

            const seen = new Set();
            const parseZIndex = (value) => {
                const parsed = Number.parseInt(value || '', 10);
                return Number.isFinite(parsed) ? parsed : 0;
            };
            const isVisible = (node) => {
                if (!(node instanceof HTMLElement)) return false;
                const rect = node.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(node);
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                if (style.opacity === '0') return false;
                return true;
            };
            const surfaceCandidates = Array.from(document.querySelectorAll(topLayerSelector))
                .filter(isVisible)
                .map((node) => {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    const centerX = Math.min(
                        window.innerWidth - 1,
                        Math.max(0, rect.left + rect.width / 2)
                    );
                    const centerY = Math.min(
                        window.innerHeight - 1,
                        Math.max(0, rect.top + rect.height / 2)
                    );
                    const hit = document.elementFromPoint(centerX, centerY);
                    const role = node.getAttribute('role') || '';
                    const area = rect.width * rect.height;

                    let score = parseZIndex(style.zIndex);
                    if (node.getAttribute('aria-modal') === 'true') score += 500;
                    if (role === 'alertdialog') score += 420;
                    else if (role === 'dialog') score += 360;
                    else if (role === 'listbox' || role === 'menu') score += 240;
                    if (style.position === 'fixed') score += 80;
                    else if (style.position === 'absolute') score += 40;
                    if (hit instanceof HTMLElement && (node === hit || node.contains(hit) || hit.contains(node))) {
                        score += 120;
                    }
                    score += Math.min(120, area / 15000);
                    return { node, score };
                })
                .sort((a, b) => b.score - a.score);
            const activeSurface = surfaceCandidates[0]?.node || null;
            const activeSurfaceElements = activeSurface
                ? Array.from(activeSurface.querySelectorAll(selectors.join(','))).filter(isVisible)
                : [];
            const hasActiveSurfaceElements = activeSurfaceElements.length > 0;

            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(node => {
                    if (seen.has(node)) return;
                    seen.add(node);

                    const rect = node.getBoundingClientRect();
                    if (!isVisible(node)) return;

                    let name = node.getAttribute('aria-label') || '';
                    if (!name && (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA')) {
                        name = node.getAttribute('placeholder') || '';
                        if (!name) {
                            const label = node.labels && node.labels[0];
                            if (label) name = label.innerText || '';
                        }
                        if (!name) name = node.getAttribute('name') || '';
                    }
                    if (!name && node.tagName === 'SELECT') {
                        const label = node.labels && node.labels[0];
                        if (label) name = label.innerText || '';
                        if (!name) name = node.getAttribute('name') || '';
                    }
                    if (!name && (node.getAttribute('role') === 'combobox' || node.hasAttribute('aria-autocomplete'))) {
                        name = node.getAttribute('aria-label') || node.getAttribute('placeholder') || '';
                    }
                    if (!name) name = (node.innerText || node.textContent || '');
                    name = name.trim().replace(/\\s+/g, ' ').slice(0, 100);
                    if (!name) return;

                    let role = node.getAttribute('role') || node.tagName.toLowerCase();
                    const placeholder = (node.getAttribute('placeholder') || '').trim().slice(0, 100);
                    const rawValue =
                        ('value' in node && typeof node.value === 'string' && node.value) ||
                        node.getAttribute('aria-valuetext') ||
                        node.getAttribute('data-value') ||
                        '';
                    const currentValue = String(rawValue).trim().replace(/\\s+/g, ' ').slice(0, 100);
                    const isTypeahead =
                        role === 'combobox' ||
                        node.tagName === 'SELECT' ||
                        node.hasAttribute('aria-autocomplete') ||
                        node.getAttribute('aria-haspopup') === 'listbox' ||
                        node.closest('[role="combobox"]') !== null;
                    const isRequired = (() => {
                        if (node.hasAttribute('required')) return true;
                        if (node.getAttribute('aria-required') === 'true') return true;
                        // Check associated label text for a * or "required" hint
                        const labelEl = (node.labels && node.labels[0]) ||
                            (node.id ? document.querySelector(`label[for="${CSS.escape(node.id)}"]`) : null);
                        if (labelEl) {
                            const labelText = labelEl.textContent || '';
                            if (labelText.includes('*') || /\\brequired\\b/i.test(labelText)) return true;
                        }
                        // Also check nearby sibling text nodes for a * marker
                        const parent = node.parentElement;
                        if (parent) {
                            const parentText = parent.textContent || '';
                            if (parentText.includes('*')) return true;
                        }
                        return false;
                    })();
                    const expandedAttr = node.getAttribute('aria-expanded');
                    const isExpanded = expandedAttr == null ? null : expandedAttr === 'true';
                    const inActiveSurface =
                        activeSurface instanceof HTMLElement && activeSurface.contains(node);
                    const layerHost = node.closest(topLayerSelector);

                    let score = 0;
                    if (chatAreaSelector) {
                        try {
                            const chatArea = document.querySelector(chatAreaSelector);
                            if (chatArea && chatArea.contains(node)) {
                                score += 100;
                            } else if (chatArea) {
                                const chatRect = chatArea.getBoundingClientRect();
                                const distance = Math.abs(rect.top - chatRect.top) +
                                                Math.abs(rect.left - chatRect.left);
                                if (distance < 500) score += Math.max(0, 50 - distance / 10);
                            }
                        } catch (e) {}
                    }
                    if (role === 'button' || node.tagName === 'BUTTON') score += 20;
                    else if (role === 'link' || node.tagName === 'A') score += 10;
                    else if (role === 'combobox' || node.tagName === 'SELECT') score += 18;
                    else if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') score += 12;

                    const nl = name.toLowerCase();
                    if (nl.includes('submit') || nl.includes('confirm') || nl.includes('continue'))
                        score += 15;
                    if (isTypeahead) score += 8;
                    if (nl.includes('skip') || nl.includes('cancel') ||
                        node.closest('nav') || node.closest('footer'))
                        score -= 10;
                    if (hasActiveSurfaceElements) {
                        if (inActiveSurface) {
                            score += 220;
                        } else if (
                            layerHost instanceof HTMLElement &&
                            ['option', 'menuitem'].includes(role)
                        ) {
                            score += 140;
                        } else {
                            score -= 120;
                        }
                    }

                    // Store the DOM node reference for action execution
                    const idx = window.__rx_elements.length;
                    window.__rx_elements.push(node);

                    collected.push({
                        tagName: node.tagName,
                        role: role,
                        name: name,
                        placeholder: placeholder || null,
                        currentValue: currentValue || null,
                        isTypeahead: isTypeahead,
                        isExpanded: isExpanded,
                        isRequired: isRequired,
                        score: score,
                        idx: idx,
                    });
                });
            });

            collected.sort((a, b) => b.score - a.score);
            return collected;
        }""",
        chat_area_selector,
    )

    interactive_elements = []
    for elem_data in elements_data[:max_elements]:
        interactive_elements.append(
            InteractiveElement(
                id=str(elem_data["idx"]),
                role=elem_data["role"],
                name=elem_data["name"],
                tag_name=elem_data["tagName"],
                placeholder=elem_data.get("placeholder"),
                current_value=elem_data.get("currentValue"),
                is_typeahead=bool(elem_data.get("isTypeahead", False)),
                is_expanded=elem_data.get("isExpanded"),
                is_required=bool(elem_data.get("isRequired", False)),
            )
        )

    return interactive_elements


async def _detect_chat_area(page: Page) -> Optional[str]:
    """
    Detect the main chat/thread area on the page.

    Uses heuristics to find containers that likely hold chat conversations.

    Args:
        page: Playwright page object

    Returns:
        CSS selector for the chat area, or None
    """
    # Common chat/thread area selectors (in order of preference)
    selectors = [
        "[data-testid='chat-thread']",
        "[data-testid='conversation']",
        "[data-testid='messages']",
        "[role='log']",  # ARIA log role is often used for chat
        ".chat-thread",
        ".conversation",
        ".messages",
        "#chat",
        "#conversation",
        "main",  # Main content area
    ]

    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Check if visible and has content
                is_visible = await element.is_visible()
                if is_visible:
                    # Check if it has multiple children (likely a container)
                    has_children = await element.evaluate(
                        "el => el.children && el.children.length > 2"
                    )
                    if has_children:
                        return selector
        except Exception:
            continue

    return None


async def detect_chat_input(page: Page) -> Optional[str]:
    """
    Detect chat input field using enhanced heuristics.

    Tries multiple strategies to find the most likely chat input field.

    Args:
        page: Playwright page object

    Returns:
        Locator string for the chat input, or None if not found
    """
    # Strategy 1: Look for chat-specific data attributes
    selectors = [
        "[data-testid='chat-input']",
        "[data-testid='message-input']",
        "[data-testid='prompt-input']",
    ]

    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return selector
        except Exception:
            continue

    # Strategy 2: Look for textarea with chat-related placeholders
    textarea_selectors = [
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='chat' i]",
        "textarea[placeholder*='type' i]",
        "textarea[placeholder*='ask' i]",
        "textarea[placeholder*='write' i]",
        "textarea[placeholder*='prompt' i]",
    ]

    for selector in textarea_selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return selector
        except Exception:
            continue

    # Strategy 3: Look for input fields with chat-related attributes
    input_selectors = [
        "input[placeholder*='message' i]",
        "input[placeholder*='chat' i]",
        "input[name='message' i]",
        "input[name='chat' i]",
        "input[name='prompt' i]",
    ]

    for selector in input_selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return selector
        except Exception:
            continue

    # Strategy 4: Look for contenteditable divs (common in modern chat apps)
    contenteditable_selectors = [
        "div[contenteditable='true']:not([aria-hidden])",
        "div[contenteditable='plaintext-only']:not([aria-hidden])",
    ]

    for selector in contenteditable_selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                # Check if it's likely a chat input (has aria-label or placeholder)
                aria_label = await element.get_attribute("aria-label")
                placeholder = await element.get_attribute("placeholder")
                role = await element.get_attribute("role")

                if aria_label and any(
                    word in aria_label.lower()
                    for word in ["message", "chat", "prompt", "type", "write"]
                ):
                    return selector
                if placeholder and any(
                    word in placeholder.lower()
                    for word in ["message", "chat", "prompt", "type", "write"]
                ):
                    return selector
                if role == "textbox":
                    return selector
        except Exception:
            continue

    # Strategy 5: Find any textarea in the chat area
    chat_area = await _detect_chat_area(page)
    if chat_area:
        try:
            # Look for textarea within chat area
            textarea_in_chat = await page.query_selector(f"{chat_area} textarea")
            if textarea_in_chat and await textarea_in_chat.is_visible():
                return f"{chat_area} textarea"

            # Look for contenteditable in chat area
            contenteditable_in_chat = await page.query_selector(
                f"{chat_area} div[contenteditable='true']"
            )
            if contenteditable_in_chat and await contenteditable_in_chat.is_visible():
                return f"{chat_area} div[contenteditable='true']"
        except Exception:
            pass

    # Strategy 6: Fallback to any visible textarea or input[type="text"]
    fallback_selectors = [
        "textarea:not([disabled])",
        "input[type='text']:not([disabled])",
    ]

    for selector in fallback_selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
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
