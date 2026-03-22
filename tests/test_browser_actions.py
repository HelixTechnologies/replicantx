from datetime import datetime, timezone

import pytest
from playwright.async_api import async_playwright

from replicantx.models import BrowserAction, BrowserObservation, InteractiveElement
from replicantx.tools.browser.actions import (
    _choice_values_match,
    _execute_click,
    _execute_fill,
    _format_action_failure,
    _looks_like_phone_value,
    _parse_element_index,
    _phone_format_variants,
    execute_action,
)
from replicantx.tools.browser.observation import extract_interactive_elements


def test_looks_like_phone_value() -> None:
    assert _looks_like_phone_value("+447797766111") is True
    assert _looks_like_phone_value("07797766111") is True
    assert _looks_like_phone_value("not a phone") is False
    assert _looks_like_phone_value("+44") is False


def test_phone_format_variants_generic() -> None:
    v = _phone_format_variants("+447797766111")
    assert "+447797766111" in v
    assert "447797766111" in v
    assert "07797766111" in v


def test_phone_format_variants_us_nanp() -> None:
    v = _phone_format_variants("+15551234567")
    assert "+15551234567" in v
    assert "5551234567" in v


def test_choice_values_match_handles_month_abbreviations() -> None:
    assert _choice_values_match("Jan", "January") is True
    assert _choice_values_match("September", "Sep") is True


def test_parse_element_index_rejects_non_numeric_targets() -> None:
    assert _parse_element_index("25") == 25
    assert _parse_element_index(" 7 ") == 7
    assert _parse_element_index("?") is None
    assert _parse_element_index("element 7") is None


@pytest.mark.asyncio
async def test_execute_click_prefers_nested_view_rates_button_in_click_proxy() -> None:
    html = """
    <div id="room-card" role="button" tabindex="0" style="position: relative; width: 320px; padding: 16px; border: 1px solid #ccc;">
      <div class="room-content-compact" style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <div class="room-info-main">
          <div>Classic Room</div>
          <div>Breakfast included</div>
        </div>
        <div class="room-pricing-action">
          <button id="view-rates" type="button">View Rates</button>
        </div>
      </div>
    </div>
    <div id="rates-panel" hidden>Rates Loaded</div>
    """

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)
        await page.evaluate(
            """() => {
                const trigger = document.getElementById('view-rates');
                const panel = document.getElementById('rates-panel');
                trigger.addEventListener('click', () => {
                    panel.hidden = false;
                });
                window.__rx_elements = [document.getElementById('room-card')];
            }"""
        )

        observation = BrowserObservation(
            url="https://app.example.test/hotel",
            title="Hotel room modal",
            visible_text="Classic Room View Rates",
            interactive_elements=[
                InteractiveElement(
                    id="0",
                    role="button",
                    name="Classic Room View Rates",
                    tag_name="DIV",
                )
            ],
            timestamp=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
        )

        success, message, _ = await _execute_click(page, "0", observation, 5)

        assert success is True, message
        assert await page.is_visible("#rates-panel") is True

        await browser.close()


@pytest.mark.asyncio
async def test_execute_action_recaptures_observation_after_overlay_click_failure() -> None:
    html = """
    <button id="background-action" type="button" style="position:absolute; top: 40px; left: 40px;">
      Continue booking
    </button>
    <div
      id="blocking-modal"
      role="dialog"
      aria-modal="true"
      style="position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35); z-index: 9999;"
    >
      <div style="margin: 80px auto; width: 280px; background: white; padding: 24px;">
        <button id="close-modal" type="button">Close</button>
      </div>
    </div>
    """

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)
        await page.evaluate(
            """() => {
                window.__rx_elements = [document.getElementById('background-action')];
            }"""
        )

        observation = BrowserObservation(
            url="https://app.example.test/booking",
            title="Booking",
            visible_text="Continue booking Close",
            interactive_elements=[
                InteractiveElement(
                    id="0",
                    role="button",
                    name="Continue booking",
                    tag_name="BUTTON",
                )
            ],
            timestamp=datetime(2026, 3, 22, 12, 15, tzinfo=timezone.utc),
        )

        result = await execute_action(
            page,
            action=BrowserAction(action_type="click", target="0"),
            action_timeout_seconds=1,
            observation=observation,
        )

        assert result.success is False
        assert result.observation is not None
        assert "blocking interaction" in result.message
        assert any(
            element.name == "Close" for element in result.observation.interactive_elements
        )

        await browser.close()


@pytest.mark.asyncio
async def test_extract_interactive_elements_prioritizes_modal_controls() -> None:
    html = """
    <main>
      <button id="background-action" type="button">Continue on background</button>
    </main>
    <div
      id="flight-modal"
      role="dialog"
      aria-modal="true"
      style="position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35); z-index: 9999;"
    >
      <div style="margin: 80px auto; width: 280px; background: white; padding: 24px;">
        <button id="confirm-modal" type="button">Confirm in modal</button>
      </div>
    </div>
    """

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)

        elements = await extract_interactive_elements(page, max_elements=1)

        assert [element.name for element in elements] == ["Confirm in modal"]

        await browser.close()


@pytest.mark.asyncio
async def test_execute_fill_uses_combobox_trigger_button_before_typing() -> None:
    html = """
    <div
      id="category-combobox"
      role="combobox"
      aria-haspopup="listbox"
      aria-controls="category-options"
      aria-expanded="false"
      style="display: inline-flex; align-items: center; gap: 8px;"
    >
      <input id="category-input" placeholder="Select category" readonly />
      <button id="category-trigger" type="button" aria-label="Open category options">▼</button>
    </div>
    <ul id="category-options" role="listbox" hidden>
      <li role="option">Business Travel</li>
      <li role="option">Conference</li>
    </ul>
    """

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)
        await page.evaluate(
            """() => {
                const combo = document.getElementById('category-combobox');
                const input = document.getElementById('category-input');
                const trigger = document.getElementById('category-trigger');
                const listbox = document.getElementById('category-options');
                const options = Array.from(listbox.querySelectorAll('[role="option"]'));

                trigger.addEventListener('click', () => {
                    listbox.hidden = false;
                    combo.setAttribute('aria-expanded', 'true');
                });

                for (const option of options) {
                    option.addEventListener('click', () => {
                        input.value = option.textContent.trim();
                        listbox.hidden = true;
                        combo.setAttribute('aria-expanded', 'false');
                    });
                }

                window.__rx_elements = [combo];
            }"""
        )

        success, message, _ = await _execute_fill(
            page,
            element_id="0",
            value="Business Travel",
            timeout_seconds=5,
        )

        assert success is True, message
        assert await page.input_value("#category-input") == "Business Travel"
        assert await page.is_hidden("#category-options") is True

        await browser.close()


@pytest.mark.asyncio
async def test_execute_fill_phone_recommits_instead_of_short_circuiting_already_shows() -> None:
    """Tel inputs skip naive 'already shows' and clear+refill+Tab to satisfy validators."""
    html = """
    <label for="guest-phone">Phone</label>
    <input type="tel" id="guest-phone" name="phone" value="+447797766111" />
    """

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)
        await page.evaluate(
            """() => {
                window.__rx_elements = [document.getElementById('guest-phone')];
            }"""
        )

        success, message, _ = await _execute_fill(
            page,
            element_id="0",
            value="+447797766111",
            timeout_seconds=5,
        )

        assert success is True, message
        assert "Re-committed" in message or "Filled" in message
        assert await page.input_value("#guest-phone") == "+447797766111"

        await browser.close()


def test_format_action_failure_normalizes_overlay_and_stale_dom_messages() -> None:
    assert "blocking interaction" in _format_action_failure(
        "click",
        "12",
        "ElementHandle.click: another element would receive the click",
    )
    assert "no longer exists in the DOM" in _format_action_failure(
        "fill",
        "3",
        "Element is not attached to the DOM",
    )
