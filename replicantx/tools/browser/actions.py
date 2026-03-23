# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser action execution for ReplicantX browser mode.
"""

import asyncio
import calendar
import re
import time
from typing import Optional
from playwright.async_api import Page, Locator

from replicantx.models import BrowserAction, BrowserActionResult, BrowserObservation
from replicantx.tools.browser.observation import extract_observation

_MONTH_EQUIVALENTS: dict[str, set[str]] = {}
for month_number in range(1, 13):
    full_name = calendar.month_name[month_number]
    abbreviated_name = calendar.month_abbr[month_number]
    if not full_name or not abbreviated_name:
        continue

    equivalents = {
        " ".join(full_name.lower().split()),
        " ".join(abbreviated_name.lower().split()),
    }
    for alias in list(equivalents):
        _MONTH_EQUIVALENTS[alias] = set(equivalents)


def _looks_like_phone_value(value: str) -> bool:
    """
    Heuristic: value is plausibly a phone number (E.164 or digit run).

    Kept loose so international formats work without app-specific rules.
    """
    s = value.strip()
    if not s:
        return False
    digits = re.sub(r"\D", "", s)
    if len(digits) < 8:
        return False
    if s.startswith("+"):
        return True
    return 10 <= len(digits) <= 15


def _phone_format_variants(raw: str) -> list[str]:
    """
    Generic alternative formats to try when a tel field ignores .fill() or
    validators expect a different shape (digits-only, national, etc.).

    Not app-specific: E.164-ish heuristics only (strip plus, UK +44→0…, US +1…).
    """
    s = raw.strip()
    if not s:
        return []
    digits = re.sub(r"\D", "", s)
    out: list[str] = []

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in out:
            out.append(c)

    add(s)
    if digits:
        add(digits)
    if s.startswith("+") and digits:
        add("+" + digits)
    # UK mobile/landline: +44… → 0…
    if digits.startswith("44") and len(digits) >= 12:
        add("0" + digits[2:])
    # US NANP: +1XXXXXXXXXX → 10-digit national
    if digits.startswith("1") and len(digits) == 11:
        add(digits[1:])

    return out


async def _is_phone_like_control(page: Page, element: Locator) -> bool:
    return bool(
        await page.evaluate(
            """(el) => {
                if (!(el instanceof HTMLElement)) return false;
                const tag = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                if (type === 'tel') return true;
                if (el.getAttribute('inputmode') === 'tel') return true;
                const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
                if (ac.includes('tel') || ac.includes('mobile') || ac.includes('phone')) {
                    return true;
                }
                const blob = [
                    el.getAttribute('name'),
                    el.getAttribute('id'),
                    el.getAttribute('aria-label'),
                    el.getAttribute('placeholder'),
                    el.getAttribute('data-testid'),
                ].filter(Boolean).join(' ').toLowerCase();
                return /\\bphone\\b|\\bmobile\\b|\\btel\\b|\\btelephone\\b/.test(blob);
            }""",
            element,
        )
    )


async def _fill_phone_with_format_retries(
    page: Page,
    fill_target: Locator,
    value: str,
    element_id: str,
    timeout_seconds: int,
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """
    Clear and refill tel/phone fields, trying several generic formats.

    Avoids the plain-text \"already shows\" trap: React apps often keep an
    internal value while validation/UI stay stale until blur or re-entry.
    """
    variants = _phone_format_variants(value)
    if not variants:
        return False, "No phone variants to try", None

    last_tried = variants[-1]
    for i, variant in enumerate(variants):
        try:
            await fill_target.click(timeout=timeout_seconds * 1000)
        except Exception:
            pass
        await _clear_existing_text(page, fill_target, timeout_seconds)
        try:
            await fill_target.fill(variant, timeout=timeout_seconds * 1000)
        except Exception:
            await page.keyboard.type(variant, delay=25)
        await asyncio.sleep(0.12)
        try:
            await page.keyboard.press("Tab")
        except Exception:
            pass
        await asyncio.sleep(0.28)

        if await _control_value_matches(page, fill_target, value) or await _control_value_matches(
            page, fill_target, variant
        ):
            new_observation = await extract_observation(page)
            if i == 0 and variant == value.strip():
                return (
                    True,
                    f"Re-committed phone on element {element_id}: {variant}",
                    new_observation,
                )
            return (
                True,
                f"Filled element {element_id} with phone (tried format {i + 1}/{len(variants)}): {variant}",
                new_observation,
            )

    new_observation = await extract_observation(page)
    return (
        False,
        f"Phone fill on element {element_id} did not stabilize after {len(variants)} format(s); last tried: {last_tried!r}",
        new_observation,
    )


_DROPDOWN_OPTION_SELECTORS = [
    "[role='option']",
    "[role='listbox'] li",
    "[role='listbox'] [role='option']",
    "[role='menu'] [role='menuitem']",
    "[data-radix-popper-content-wrapper] [role='option']",
    "[data-radix-popper-content-wrapper] [role='menuitem']",
    "[cmdk-item]",
    "ul[class*='menu'] li",
    "ul[class*='list'] li",
    "div[class*='option']",
    "div[class*='select'] div[class*='option']",
    "div[class*='menu'] div[class*='option']",
    ".rc-virtual-list .ant-select-item",
    ".ant-select-dropdown .ant-select-item-option",
    "li[data-option]",
]


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
        elif action.action_type == "compose_chat":
            success, message, new_observation = await _execute_compose_chat(
                page, action.value, action_timeout_seconds
            )
        elif action.action_type == "submit_chat":
            success, message, new_observation = await _execute_submit_chat(
                page, action_timeout_seconds
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

    if new_observation is None:
        new_observation = await _capture_post_action_observation(page)

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


async def _find_chat_input(page: Page) -> Optional[str]:
    """Detect the chat composer input using heuristics with a generic fallback."""
    from replicantx.tools.browser.observation import detect_chat_input

    selector = await detect_chat_input(page)
    if selector:
        return selector

    try:
        textarea = await page.wait_for_selector(
            "textarea, input[type='text']", timeout=5000
        )
        if textarea:
            return "textarea, input[type='text']"
    except Exception:
        pass

    return None


_SEND_BUTTON_SELECTORS = [
    "button[aria-label*='send' i]",
    "button[aria-label*='Send' i]",
    "button[data-testid*='send' i]",
    "button[type='submit']",
]


async def _find_send_button(page: Page) -> Optional[Locator]:
    """Find a visible send/submit button near the chat composer."""
    for selector in _SEND_BUTTON_SELECTORS:
        try:
            buttons = await page.query_selector_all(selector)
            for btn in buttons:
                if await btn.is_visible():
                    return btn  # type: ignore[return-value]
        except Exception:
            continue
    return None


async def _execute_compose_chat(
    page: Page, message: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """Type a message into the chat composer without submitting it.

    This allows the caller to interact with autocomplete/mention dropdowns
    before sending.
    """
    chat_input_selector = await _find_chat_input(page)
    if not chat_input_selector:
        return False, "Could not find chat input field", None

    try:
        await page.click(chat_input_selector, timeout=timeout_seconds * 1000)
        await page.keyboard.type(message, delay=30)
        await asyncio.sleep(0.3)

        new_observation = await extract_observation(page)
        return True, f"Composed chat draft: {message}", new_observation
    except Exception as e:
        return False, _format_action_failure("compose chat", None, str(e)), None


async def _execute_submit_chat(
    page: Page, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """Submit whatever is currently in the chat composer.

    Prefers clicking a visible send button; falls back to pressing Enter on
    the chat input.
    """
    send_btn = await _find_send_button(page)
    if send_btn:
        try:
            await send_btn.click(timeout=timeout_seconds * 1000)
            await _wait_for_page_settle(page, timeout_seconds)
            new_observation = await extract_observation(page)
            return True, "Submitted chat via send button", new_observation
        except Exception:
            pass

    chat_input_selector = await _find_chat_input(page)
    if not chat_input_selector:
        return False, "Could not find chat input to submit", None

    try:
        await page.press(chat_input_selector, "Enter")
        await _wait_for_page_settle(page, timeout_seconds)
        new_observation = await extract_observation(page)
        return True, "Submitted chat via Enter key", new_observation
    except Exception as e:
        return False, _format_action_failure("submit chat", None, str(e)), None


async def _execute_send_chat(
    page: Page, message: str, timeout_seconds: int
) -> tuple[bool, str, Optional[BrowserObservation]]:
    """Compose and immediately submit a chat message (legacy one-step action)."""
    chat_input_selector = await _find_chat_input(page)
    if not chat_input_selector:
        return False, "Could not find chat input field", None

    try:
        await page.fill(chat_input_selector, message, timeout=timeout_seconds * 1000)
        await page.press(chat_input_selector, "Enter")
        await _wait_for_page_settle(page, timeout_seconds)

        new_observation = await extract_observation(page)
        return True, f"Sent chat message: {message}", new_observation
    except Exception as e:
        return False, _format_action_failure("send chat", None, str(e)), None


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
    element_index = _parse_element_index(element_id)
    if element_index is None:
        return (
            False,
            f"Invalid element target {element_id!r}; expected a numeric element ID from the current page",
            None,
        )

    target_name = element_id
    if observation:
        for elem in observation.interactive_elements:
            if elem.id == element_id:
                target_name = f"{elem.role}: {elem.name}"
                break

    try:
        handle = await page.evaluate_handle(
            "(elementIndex) => window.__rx_elements && window.__rx_elements[elementIndex]",
            element_index,
        )
        is_valid = await page.evaluate("el => el instanceof HTMLElement", handle)
        if not is_valid:
            return False, f"Element {element_id} no longer exists in the DOM", None

        element = handle.as_element()
        click_target = await _resolve_click_target(page, element)
        await click_target.click(timeout=timeout_seconds * 1000)
        await _wait_for_page_settle(page, timeout_seconds)
        new_observation = await extract_observation(page)
        return True, f"Clicked {target_name}", new_observation
    except Exception as e:
        return False, _format_action_failure("click", element_id, str(e)), None


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

    element_index = _parse_element_index(element_id)
    if element_index is None:
        return (
            False,
            f"Invalid element target {element_id!r}; expected a numeric element ID from the current page",
            None,
        )

    try:
        handle = await page.evaluate_handle(
            "(elementIndex) => window.__rx_elements && window.__rx_elements[elementIndex]",
            element_index,
        )
        is_valid = await page.evaluate("el => el instanceof HTMLElement", handle)
        if not is_valid:
            return False, f"Element {element_id} no longer exists in the DOM", None

        element = handle.as_element()
        fill_target = await _resolve_fill_target(page, element)

        is_phone_field = await _is_phone_like_control(page, fill_target) and _looks_like_phone_value(
            value
        )

        # Tel/phone inputs: never trust "already shows" alone — masked UIs, split
        # widgets, and React controlled fields often need clear + refill + blur.
        if not is_phone_field and await _control_value_matches(page, fill_target, value):
            new_observation = await extract_observation(page)
            return True, f"Element {element_id} already shows: {value}", new_observation

        if await _is_native_select(page, fill_target):
            if await _select_native_option(page, fill_target, value):
                await asyncio.sleep(0.3)
                new_observation = await extract_observation(page)
                return True, f"Selected \"{value}\" from dropdown for element {element_id}", new_observation

        is_typeahead = await _is_typeahead_control(page, fill_target)

        if is_typeahead:
            await _open_typeahead_dropdown(page, fill_target, timeout_seconds)
            await _wait_for_dropdown_options(page, fill_target, timeout_seconds)

            selected = await _try_select_dropdown_option(
                page, fill_target, value, timeout_seconds
            )
            if not selected:
                await _clear_existing_text(page, fill_target, timeout_seconds)
                try:
                    await fill_target.fill(value, timeout=timeout_seconds * 1000)
                except Exception:
                    await page.keyboard.type(value, delay=30)
                # Wait for the dropdown to (re-)appear after typing/filtering
                await _wait_for_dropdown_options(page, fill_target, timeout_seconds)
                selected = await _try_select_dropdown_option(
                    page, fill_target, value, timeout_seconds
                )
            if not selected:
                selected = await _try_commit_typeahead_value(page, fill_target, value)

            await asyncio.sleep(0.3)
            new_observation = await extract_observation(page)

            if selected:
                return True, f"Selected \"{value}\" from dropdown for element {element_id}", new_observation

            if await _control_value_matches(page, fill_target, value):
                return True, f"Filled element {element_id} with: {value}", new_observation

            return False, f'Failed to select "{value}" from combobox element {element_id}', new_observation

        if is_phone_field:
            return await _fill_phone_with_format_retries(
                page, fill_target, value, element_id, timeout_seconds
            )

        await fill_target.click(timeout=timeout_seconds * 1000)
        await _clear_existing_text(page, fill_target, timeout_seconds)

        try:
            await fill_target.fill(value, timeout=timeout_seconds * 1000)
        except Exception:
            await page.keyboard.type(value, delay=30)

        await asyncio.sleep(0.4)
        await asyncio.sleep(0.3)
        new_observation = await extract_observation(page)

        if await _control_value_matches(page, fill_target, value):
            return True, f"Filled element {element_id} with: {value}", new_observation

        return True, f"Typed \"{value}\" into element {element_id}", new_observation
    except Exception as e:
        return False, _format_action_failure("fill", element_id, str(e)), None


def _parse_element_index(element_id: Optional[str]) -> Optional[int]:
    if element_id is None:
        return None

    normalized = str(element_id).strip()
    if not normalized.isdigit():
        return None

    return int(normalized)


async def _resolve_click_target(page: Page, element: Locator) -> Locator:
    target_handle = await page.evaluate_handle(
        """(el) => {
            if (!(el instanceof HTMLElement)) return el;

            const clickableSelector = [
                'button:not([disabled])',
                'a[href]',
                'input:not([type="hidden"]):not([disabled])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                'summary',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[role="option"]',
                '[role="tab"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="switch"]',
                '[aria-expanded]',
                '[aria-haspopup]',
                '[data-radix-select-trigger]'
            ].join(',');

            const isClickable = (node) => {
                if (!(node instanceof HTMLElement)) return false;
                const rect = node.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const tagName = node.tagName.toLowerCase();
                const role = node.getAttribute('role');
                if (node.matches(clickableSelector)) return true;
                if (['button', 'a', 'input', 'textarea', 'select', 'summary', 'label'].includes(tagName)) return true;
                if (role && ['button', 'link', 'menuitem', 'option', 'tab', 'checkbox', 'radio', 'switch'].includes(role)) return true;
                const tabIndex = node.getAttribute('tabindex');
                return tabIndex !== null && tabIndex !== '-1';
            };

            const normalizeText = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
            const actionHints = [
                'view rates',
                'rates',
                'rate',
                'choose',
                'select',
                'book',
                'add',
                'continue',
                'confirm',
                'submit',
                'save',
                'close',
                'next'
            ];

            const describe = (node) => {
                const ariaLabel = node.getAttribute('aria-label');
                if (ariaLabel) return normalizeText(ariaLabel);
                if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
                    const placeholder = node.getAttribute('placeholder');
                    if (placeholder) return normalizeText(placeholder);
                }
                return normalizeText(node.innerText || node.textContent || '');
            };

            const samplePoints = (rect) => {
                if (rect.width <= 0 || rect.height <= 0) return [];
                return [
                    [0.5, 0.5],
                    [0.25, 0.5],
                    [0.75, 0.5],
                    [0.5, 0.25],
                    [0.5, 0.75],
                ].map(([xRatio, yRatio]) => ({
                    x: rect.left + rect.width * xRatio,
                    y: rect.top + rect.height * yRatio,
                }));
            };

            const isHitTarget = (candidate, hit) => {
                if (!(candidate instanceof HTMLElement) || !(hit instanceof HTMLElement)) return false;
                return candidate === hit || candidate.contains(hit) || hit.contains(candidate);
            };

            const isLeafActionableControl = (node) => {
                if (!(node instanceof HTMLElement)) return false;
                if (!isClickable(node)) return false;
                const tagName = node.tagName.toLowerCase();
                const role = node.getAttribute('role') || '';
                return (
                    ['button', 'a', 'input', 'textarea', 'select', 'summary'].includes(tagName) ||
                    ['button', 'link', 'menuitem', 'option', 'tab', 'checkbox', 'radio', 'switch'].includes(role) ||
                    node.hasAttribute('aria-expanded') ||
                    node.hasAttribute('aria-haspopup') ||
                    node.hasAttribute('data-radix-select-trigger')
                );
            };

            const rootText = describe(el).toLowerCase();
            const clickableDescendants = Array.from(el.querySelectorAll(clickableSelector))
                .filter(isClickable);
            const descendantsExist = clickableDescendants.length > 0;

            const scoredCandidates = [el, ...clickableDescendants]
                .filter(isClickable)
                .map((candidate) => {
                    const rect = candidate.getBoundingClientRect();
                    const text = describe(candidate).toLowerCase();
                    const tagName = candidate.tagName.toLowerCase();
                    const role = candidate.getAttribute('role') || '';
                    const nestedClickables = Array.from(candidate.querySelectorAll(clickableSelector))
                        .filter((node) => node !== candidate && isClickable(node));
                    const area = Math.max(1, rect.width * rect.height);
                    const topHit = samplePoints(rect).some((point) => {
                        const hit = document.elementFromPoint(point.x, point.y);
                        return isHitTarget(candidate, hit);
                    });

                    let score = 0;
                    if (tagName === 'button') score += 80;
                    else if (tagName === 'summary') score += 70;
                    else if (tagName === 'a') score += 60;
                    else if (role === 'button') score += 55;
                    else if (role && ['link', 'menuitem', 'option', 'tab', 'checkbox', 'radio', 'switch'].includes(role)) score += 45;
                    else score += 20;

                    if (text) score += 12;
                    if (text && rootText && (rootText.includes(text) || text.includes(rootText))) score += 12;
                    if (actionHints.some((hint) => text.includes(hint))) score += 35;
                    if (candidate.hasAttribute('aria-expanded')) score += 18;
                    if (candidate.hasAttribute('aria-haspopup')) score += 14;
                    if (candidate.hasAttribute('data-radix-select-trigger')) score += 20;
                    if (isLeafActionableControl(candidate)) score += 25;
                    if (topHit) score += 20;

                    score -= nestedClickables.length * 12;
                    score -= Math.log(area);

                    if (candidate === el && descendantsExist) {
                        const genericWrapper =
                            ['div', 'span', 'section', 'article', 'li'].includes(tagName) ||
                            (role === 'button' && nestedClickables.length > 0);
                        if (genericWrapper) score -= 45;
                    }

                    return { candidate, score, topHit, nestedClickables: nestedClickables.length };
                })
                .sort((a, b) => {
                    if (a.topHit !== b.topHit) return a.topHit ? -1 : 1;
                    if (a.score !== b.score) return b.score - a.score;
                    return a.nestedClickables - b.nestedClickables;
                });

            return scoredCandidates[0]?.candidate || el;
        }""",
        element,
    )
    target = target_handle.as_element()
    return target if target is not None else element


async def _resolve_fill_target(page: Page, element: Locator) -> Locator:
    target_handle = await page.evaluate_handle(
        """(el) => {
            const selectors = [
                'input:not([type="hidden"])',
                'textarea',
                'select',
                '[role="combobox"]',
                '[aria-autocomplete]',
                '[contenteditable="true"]',
                '[contenteditable=""]'
            ];

            const isEditable = (node) => {
                if (!node || !(node instanceof HTMLElement)) return false;
                if (node.matches('input:not([type="hidden"]), textarea, select')) return true;
                if (node.getAttribute('role') === 'combobox') return true;
                if (node.hasAttribute('aria-autocomplete')) return true;
                if (node.isContentEditable) return true;
                return false;
            };

            if (isEditable(el)) return el;
            for (const selector of selectors) {
                const match = el.querySelector(selector);
                if (isEditable(match)) return match;
            }
            return el;
        }""",
        element,
    )
    target = target_handle.as_element()
    return target if target is not None else element


async def _is_native_select(page: Page, element: Locator) -> bool:
    return bool(
        await page.evaluate(
            """(el) => {
                return el instanceof HTMLSelectElement;
            }""",
            element,
        )
    )


async def _is_typeahead_control(page: Page, element: Locator) -> bool:
    return bool(
        await page.evaluate(
            """(el) => {
                if (!(el instanceof HTMLElement)) return false;
                const role = el.getAttribute('role');
                return (
                    role === 'combobox' ||
                    el.tagName === 'SELECT' ||
                    el.hasAttribute('aria-autocomplete') ||
                    el.getAttribute('aria-haspopup') === 'listbox' ||
                    el.closest('[role="combobox"]') !== null
                );
            }""",
            element,
        )
    )


async def _resolve_combobox_trigger(page: Page, element: Locator) -> Optional[Locator]:
    target_handle = await page.evaluate_handle(
        """(el) => {
            if (!(el instanceof HTMLElement)) return null;

            const roots = [
                el,
                el.closest('[role="combobox"]'),
                el.closest('[aria-haspopup="listbox"]'),
                el.closest('[data-radix-select-trigger]'),
                el.parentElement,
                el.parentElement?.parentElement,
            ].filter((node) => node instanceof HTMLElement);

            const selectors = [
                'button:not([disabled])',
                '[role="button"]',
                '[aria-haspopup="listbox"]',
                '[aria-expanded]',
                '[data-radix-select-trigger]',
                '[class*="trigger"]',
                '[class*="indicator"]',
                '[class*="chevron"]',
                '[class*="arrow"]',
            ].join(',');

            const seen = new Set();
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const isVisible = (node) => {
                if (!(node instanceof HTMLElement)) return false;
                const rect = node.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(node);
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                return true;
            };
            const isEditable = (node) => {
                if (!(node instanceof HTMLElement)) return false;
                return Boolean(
                    node.matches('input:not([type="hidden"]), textarea, select') ||
                    node.getAttribute('role') === 'combobox' ||
                    node.hasAttribute('aria-autocomplete') ||
                    node.isContentEditable
                );
            };
            const isClearButton = (text) =>
                ['clear', 'remove', 'delete', 'close', 'reset'].some((marker) => text.includes(marker));

            const candidates = [];
            for (const root of roots) {
                const pool = [root, ...Array.from(root.querySelectorAll(selectors))];
                for (const candidate of pool) {
                    if (!(candidate instanceof HTMLElement) || seen.has(candidate)) continue;
                    seen.add(candidate);
                    if (!isVisible(candidate) || isEditable(candidate)) continue;

                    const rect = candidate.getBoundingClientRect();
                    const label = normalize(
                        candidate.getAttribute('aria-label') ||
                        candidate.getAttribute('title') ||
                        candidate.textContent
                    );
                    const role = candidate.getAttribute('role') || '';

                    let score = 0;
                    if (candidate.hasAttribute('data-radix-select-trigger')) score += 90;
                    if (candidate.getAttribute('aria-haspopup') === 'listbox') score += 85;
                    if (candidate.hasAttribute('aria-expanded')) score += 50;
                    if (candidate.tagName.toLowerCase() === 'button') score += 35;
                    if (role === 'button') score += 25;
                    if (label && ['open', 'select', 'choose', 'show', 'options', 'dropdown'].some((hint) => label.includes(hint))) {
                        score += 35;
                    }
                    if (isClearButton(label)) score -= 120;
                    if (rect.width <= 72) score += 18;
                    if (rect.height <= 48) score += 8;
                    if (!label) score += 6;
                    if (candidate.contains(el) || el.contains(candidate)) score += 10;

                    candidates.push({ candidate, score });
                }
            }

            candidates.sort((a, b) => b.score - a.score);
            return candidates[0]?.candidate || null;
        }""",
        element,
    )
    target = target_handle.as_element()
    return target if target is not None else None


async def _open_typeahead_dropdown(
    page: Page,
    element: Locator,
    timeout_seconds: int,
) -> bool:
    if await _has_visible_dropdown_options(page, element):
        return True

    trigger = await _resolve_combobox_trigger(page, element)
    click_targets = [candidate for candidate in (trigger, element) if candidate is not None]
    for target in click_targets:
        try:
            await target.click(timeout=timeout_seconds * 1000)
            await asyncio.sleep(0.2)
        except Exception:
            continue
        if await _has_visible_dropdown_options(page, element):
            return True

    for key in ("ArrowDown", "Enter", "Space"):
        try:
            await element.focus()
            await page.keyboard.press(key)
            await asyncio.sleep(0.2)
        except Exception:
            continue
        if await _has_visible_dropdown_options(page, element):
            return True

    return False


async def _clear_existing_text(page: Page, element: Locator, timeout_seconds: int) -> None:
    await element.click(timeout=timeout_seconds * 1000)
    select_all = "Meta+A" if hasattr(page.context.browser, "browser_type") else "Meta+A"
    try:
        await page.keyboard.press(select_all)
    except Exception:
        try:
            await page.keyboard.press("Control+A")
        except Exception:
            pass
    try:
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    try:
        await element.fill("", timeout=1500)
    except Exception:
        pass


async def _read_control_value(page: Page, element: Locator) -> str:
    value = await page.evaluate(
        """(el) => {
            if (!(el instanceof HTMLElement)) return '';

            // For plain inputs and textareas, .value is the only reliable source.
            // Do NOT read from parent/wrapper elements — they may contain unrelated
            // page text (labels, chat history, etc.) that would cause false matches.
            if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
                return el.value || '';
            }

            if (el instanceof HTMLSelectElement) {
                const selected = Array.from(el.selectedOptions || [])
                    .map(o => (o.label || o.textContent || o.value || '').trim())
                    .filter(Boolean);
                return selected[0] || el.value || '';
            }

            const values = [];
            const seen = new Set();

            const pushValue = (rawValue) => {
                if (rawValue == null) return;
                const normalized = String(rawValue).replace(/\\s+/g, ' ').trim();
                if (!normalized) return;
                if (seen.has(normalized)) return;
                seen.add(normalized);
                values.push(normalized);
            };

            const pushNodeValue = (node) => {
                if (!(node instanceof HTMLElement)) return;

                if (node instanceof HTMLSelectElement) {
                    for (const option of Array.from(node.selectedOptions || [])) {
                        pushValue(option.label || option.textContent || option.value);
                    }
                }

                // For nested inputs/textareas use .value only, never innerText
                if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement) {
                    pushValue(node.value);
                    return;
                }

                const directValue =
                    node.getAttribute('aria-valuetext') ||
                    node.getAttribute('data-value');
                pushValue(directValue);

                const activeDescendantId = node.getAttribute('aria-activedescendant');
                if (activeDescendantId) {
                    const activeDescendant = document.getElementById(activeDescendantId);
                    if (activeDescendant instanceof HTMLElement) {
                        pushValue(activeDescendant.innerText || activeDescendant.textContent || '');
                    }
                }

                // Only read innerText from the element itself, not from parents
                if (node === el) {
                    pushValue(node.innerText || node.textContent || '');
                }
            };

            const comboRoot = el.closest('[role="combobox"], [aria-haspopup="listbox"], [data-radix-select-trigger], [class*="select"]');
            const nested = el.querySelector('input, textarea, select, [role="combobox"], [contenteditable="true"], [contenteditable=""]');
            const comboNested = comboRoot instanceof HTMLElement
                ? comboRoot.querySelector('input, textarea, select, [role="combobox"], [contenteditable="true"], [contenteditable=""]')
                : null;

            // Deliberately omit el.parentElement — reading parent text causes false
            // matches when a form container includes labels or chat history text.
            for (const node of [el, nested, comboRoot, comboNested]) {
                pushNodeValue(node);
            }

            return values[0] || '';
        }""",
        element,
    )
    return " ".join(str(value).split())


def _normalize_choice_text(value: str) -> str:
    return " ".join(value.lower().split())


def _equivalent_choice_values(value: str) -> set[str]:
    normalized = _normalize_choice_text(value)
    if not normalized:
        return set()

    equivalents = {normalized}
    if normalized in _MONTH_EQUIVALENTS:
        equivalents.update(_MONTH_EQUIVALENTS[normalized])

    if len(normalized) >= 3:
        equivalents.add(normalized[:3])

    return {candidate for candidate in equivalents if candidate}


def _choice_values_match(current_value: str, expected_value: str) -> bool:
    current_equivalents = _equivalent_choice_values(current_value)
    expected_equivalents = _equivalent_choice_values(expected_value)
    if not current_equivalents or not expected_equivalents:
        return False

    for current_candidate in current_equivalents:
        for expected_candidate in expected_equivalents:
            if current_candidate == expected_candidate:
                return True
            if current_candidate in expected_candidate or expected_candidate in current_candidate:
                return True

    return False


async def _control_value_matches(page: Page, element: Locator, value: str) -> bool:
    current_value = await _read_control_value(page, element)
    return _choice_values_match(current_value, value)


async def _select_native_option(page: Page, element: Locator, value: str) -> bool:
    option_value = await element.evaluate(
        """(el, requestedValue) => {
            if (!(el instanceof HTMLSelectElement)) return null;

            const normalize = (rawValue) =>
                String(rawValue || '').replace(/\\s+/g, ' ').trim().toLowerCase();

            const requested = normalize(requestedValue);
            if (!requested) return null;

            for (const option of Array.from(el.options)) {
                const candidates = [
                    normalize(option.label),
                    normalize(option.textContent),
                    normalize(option.value),
                ].filter(Boolean);

                if (candidates.some((candidate) =>
                    candidate === requested ||
                    candidate.includes(requested) ||
                    requested.includes(candidate)
                )) {
                    return option.value;
                }
            }

            return null;
        }""",
        value,
    )

    if not option_value:
        return False

    try:
        await element.select_option(value=option_value)
    except Exception:
        return False

    await asyncio.sleep(0.2)
    return await _control_value_matches(page, element, value)


async def _wait_for_dropdown_options(
    page: Page,
    element: Locator,
    timeout_seconds: int,
    max_wait_seconds: float = 2.5,
) -> bool:
    """
    Poll until dropdown options become visible, or the timeout elapses.

    Returns True as soon as any option is detected so the caller can proceed
    with selection immediately rather than sleeping for a fixed duration.
    """
    deadline = asyncio.get_event_loop().time() + min(timeout_seconds, max_wait_seconds)
    poll_interval = 0.15
    while asyncio.get_event_loop().time() < deadline:
        if await _has_visible_dropdown_options(page, element):
            return True
        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 0.5)
    return False


async def _try_commit_typeahead_value(
    page: Page, element: Locator, value: str
) -> bool:
    active_descendant_id = await page.evaluate(
        """(el) => {
            if (!(el instanceof HTMLElement)) return null;
            return (
                el.getAttribute('aria-activedescendant') ||
                el.closest('[role="combobox"]')?.getAttribute('aria-activedescendant') ||
                null
            );
        }""",
        element,
    )
    if active_descendant_id:
        try:
            active_option = await page.query_selector(f"#{active_descendant_id}")
            if active_option and await active_option.is_visible():
                await active_option.click()
                await asyncio.sleep(0.2)
                if await _control_value_matches(page, element, value):
                    return True
        except Exception:
            pass

    for key in ("ArrowDown", "Enter"):
        try:
            await page.keyboard.press(key)
            await asyncio.sleep(0.2)
        except Exception:
            continue
    if await _control_value_matches(page, element, value):
        return True

    try:
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.2)
    except Exception:
        return False
    return await _control_value_matches(page, element, value)


async def _get_associated_dropdown_selectors(
    page: Page, element: Locator
) -> list[str]:
    selectors = await page.evaluate(
        """(el) => {
            const selectorSet = new Set();
            if (!(el instanceof HTMLElement)) return [];

            const ids = [
                el.getAttribute('aria-controls'),
                el.getAttribute('aria-owns'),
                el.getAttribute('aria-describedby'),
                el.getAttribute('aria-activedescendant')
            ].filter(Boolean);

            for (const id of ids) {
                selectorSet.add(`#${CSS.escape(id)}`);
            }

            const comboRoot = el.closest('[role="combobox"], [aria-haspopup="listbox"], [data-radix-select-trigger], [class*="select"]');
            if (comboRoot instanceof HTMLElement) {
                const rootIds = [
                    comboRoot.getAttribute('aria-controls'),
                    comboRoot.getAttribute('aria-owns'),
                    comboRoot.getAttribute('aria-activedescendant')
                ].filter(Boolean);
                for (const id of rootIds) {
                    selectorSet.add(`#${CSS.escape(id)}`);
                }
            }

            return Array.from(selectorSet);
        }""",
        element,
    )
    return [selector for selector in selectors if selector]


async def _click_matching_option_in_scope(
    page: Page,
    scope_selector: str,
    value: str,
    timeout_seconds: int,
) -> bool:
    value_lower = value.lower().strip()
    value_words = set(value_lower.split())
    scoped_option_selectors = [
        f"{scope_selector} [role='option']",
        f"{scope_selector} [role='menuitem']",
        f"{scope_selector} li",
        f"{scope_selector} [cmdk-item]",
        f"{scope_selector} .ant-select-item-option",
        f"{scope_selector} [class*='option']",
    ]

    for selector in scoped_option_selectors:
        try:
            options = await page.query_selector_all(selector)
            for opt in options:
                if not await opt.is_visible():
                    continue
                text = (await opt.inner_text()).strip()
                if not text:
                    continue
                t = text.lower()
                matches = (
                    value_lower in t
                    or t in value_lower
                    or (value_words and len(value_words & set(t.split())) >= max(1, len(value_words) // 2))
                )
                if matches:
                    await opt.click(timeout=timeout_seconds * 1000)
                    return True
        except Exception:
            continue

    return False


async def _has_visible_dropdown_options(
    page: Page,
    element: Locator,
) -> bool:
    associated_selectors = await _get_associated_dropdown_selectors(page, element)
    scoped_option_selectors = [
        "[role='option']",
        "[role='menuitem']",
        "li",
        "[cmdk-item]",
        ".ant-select-item-option",
        "[class*='option']",
    ]
    for scope_selector in associated_selectors:
        for selector in scoped_option_selectors:
            if await _selector_has_visible_match(page, f"{scope_selector} {selector}"):
                return True

    for selector in _DROPDOWN_OPTION_SELECTORS:
        if await _selector_has_visible_match(page, selector):
            return True

    return False


async def _selector_has_visible_match(page: Page, selector: str) -> bool:
    try:
        options = await page.query_selector_all(selector)
    except Exception:
        return False

    for option in options:
        try:
            if await option.is_visible():
                return True
        except Exception:
            continue
    return False


async def _try_select_dropdown_option(
    page: Page, element: Locator, value: str, timeout_seconds: int
) -> bool:
    """
    After typing into a combobox/select, look for a visible dropdown
    option that matches the value and click it.

    Handles common patterns: listbox roles, data-option attributes,
    li items inside dropdown containers, etc.

    Returns True if an option was found and clicked.
    """
    value_lower = value.lower().strip()
    value_words = set(value_lower.split())

    def _text_matches(text: str) -> bool:
        t = text.lower().strip()
        if not t:
            return False
        # Direct containment
        if value_lower in t or t in value_lower:
            return True
        # Word overlap: if most words of the typed value appear in the option text
        if value_words and len(value_words & set(t.split())) >= max(1, len(value_words) // 2):
            return True
        return False

    associated_selectors = await _get_associated_dropdown_selectors(page, element)
    for scope_selector in associated_selectors:
        if await _click_matching_option_in_scope(
            page, scope_selector, value, timeout_seconds
        ):
            return True

    for selector in _DROPDOWN_OPTION_SELECTORS:
        try:
            options = await page.query_selector_all(selector)
            for opt in options:
                if not await opt.is_visible():
                    continue
                text = (await opt.inner_text()).strip()
                if _text_matches(text):
                    await opt.click(timeout=timeout_seconds * 1000)
                    return True
        except Exception:
            continue

    # Broad fallback: use Playwright's text locator to find any visible element
    # containing the value, restricted to likely dropdown containers.
    # This handles custom-styled dropdowns that don't use standard ARIA roles.
    try:
        candidates = page.get_by_text(value, exact=False)
        count = await candidates.count()
        for i in range(count):
            candidate = candidates.nth(i)
            try:
                if not await candidate.is_visible():
                    continue
                tag = await candidate.evaluate("el => el.tagName.toLowerCase()")
                # Only click leaf-level or option-like tags, not whole containers
                if tag in ("li", "div", "span", "option", "a", "p", "button"):
                    # Avoid clicking the input itself or large containers
                    box = await candidate.bounding_box()
                    if box and box["height"] < 80:
                        await candidate.click(timeout=timeout_seconds * 1000)
                        return True
            except Exception:
                continue
    except Exception:
        pass

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


async def _capture_post_action_observation(
    page: Page,
) -> Optional[BrowserObservation]:
    try:
        return await extract_observation(page)
    except Exception:
        return None


def _format_action_failure(
    action_name: str,
    element_id: Optional[str],
    error_text: str,
) -> str:
    normalized_error = " ".join(str(error_text).split())
    lower_error = normalized_error.lower()
    target_suffix = f" element {element_id}" if element_id else ""

    if (
        "intercepts pointer events" in lower_error
        or "another element would receive the click" in lower_error
        or "subtree intercepts pointer events" in lower_error
    ):
        return (
            f"Failed to {action_name}{target_suffix}: a visible overlay, modal, or "
            "drawer is blocking interaction"
        )

    if (
        "element is not attached to the dom" in lower_error
        or "element is detached from document" in lower_error
        or "no longer attached" in lower_error
        or "stale element" in lower_error
    ):
        return (
            f"Failed to {action_name}{target_suffix}: target no longer exists in the DOM"
        )

    return f"Failed to {action_name}{target_suffix}: {normalized_error}"
