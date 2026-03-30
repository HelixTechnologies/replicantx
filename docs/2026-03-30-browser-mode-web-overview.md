# Browser Mode — Web Team Brief

**Purpose:** Copy-ready outline of ReplicantX **browser mode** for [replicantx.org](https://replicantx.org).

**Audience:** Marketing, design, and web — not a full configuration reference. Point builders to whatever canonical developer documentation you publish alongside the product.

---

## One-line pitch

**Test conversational AI products the way users actually use them: in a real browser, with an intelligent agent that chats, clicks, and fills forms — not only through raw HTTP APIs.**

---

## What it is

ReplicantX already tests agent backends over **HTTP APIs**. **Browser mode** adds **Playwright-powered** end-to-end runs against **live web apps**: the same **Level 2 (agent)** Replicant drives the UI, observes the page, and plans actions until the scenario **goal** is met (or limits are hit).

- **API mode:** Structured messages to your chat endpoint; great for contract and integration checks.
- **Browser mode:** Full UI journey — chat widgets, buttons, forms, navigation — with optional **visual** confirmation of success.

---

## Why it matters (value for the site)

| Message | Detail |
|--------|--------|
| **Real user journeys** | Validates flows that only exist in the browser (embeds, SPA routing, modals, third-party widgets). |
| **Multimodal quality** | Can combine **DOM/text** understanding with **screenshot + vision models** when the UI is hard to assert from text alone. |
| **Same harness** | Same CLI (`replicantx run`), reporting (Markdown/JSON), watch mode, parallel runs, token/cost tracking — extended for the browser. |
| **Safer automation** | Domain allowlists, configurable timeouts, traces for debugging failed runs. |
| **Optional issue workflow** | CLI can produce **structured issue bundles** and, when configured, **auto-file high-confidence GitHub issues** — without changing scenario YAML. |

---

## How it works (simple story)

1. You point a scenario at a **start URL** and set **`interaction_mode: browser`**.
2. The **Replicant** (LLM-guided “user”) gets **page observations**: visible text, ranked interactive elements, and optional screenshots depending on settings.
3. A **planner** chooses actions: e.g. type in chat, click, fill, navigate, wait.
4. **Goal evaluation** decides if the user’s objective is achieved — using **keywords**, **LLM on DOM**, **vision on screenshots**, or **hybrids** (e.g. DOM first, screenshot when uncertain).
5. You get **reports**, **artifacts** (screenshots, traces on failure), and clear **token/cost** breakdown per model role.

---

## Feature bullets (good for homepage / features page)

- **Playwright automation** — Chromium (default), Firefox, or WebKit; headless or headed for local debugging.
- **Chat-first UX** — Heuristics to find chat inputs and prioritize relevant controls.
- **Goal-driven agents** — Facts, personality, `max_turns`, and completion signals aligned with API-mode agent tests.
- **Flexible goal evidence** — From fast **DOM-only** checks to **screenshot + vision** and **recommended hybrid** (`dom_then_screenshot`) for production-style balance of speed and accuracy.
- **Auth that matches real apps** — e.g. **Supabase magic link** with **generated test users** for repeatable browser login flows.
- **Watch mode** — Live visibility into the run from the terminal.
- **Traces** — Playwright traces retained on failure (or always) for deep debugging (`playwright show-trace`).
- **Standalone browser issue triage** — CLI flags for **draft-only** bundles vs **auto-high-confidence** GitHub filing; optional **Logfire** log excerpts and **artifact uploads** for richer issues.

---

## API mode vs browser mode (comparison blurb)

| | API mode | Browser mode |
|---|----------|----------------|
| **Surface** | HTTP request/response to your API | Real browser against your deployed app |
| **Best for** | Fast regression, payload formats, auth headers | Full UI flows, visual regressions, widget-heavy UIs |
| **Setup** | `base_url` + auth for API | `playwright install` + `replicant.browser.start_url` + optional vision models |
| **Assertions** | Messages + structured checks | Goals + DOM/intelligent/hybrid evaluation + optional screenshots |

---

## Prerequisites to mention (honest, short)

- **Python 3.11+** and ReplicantX install (CLI extras as today on the site).
- **Playwright browsers** installed once (`playwright install`).
- **LLM provider keys** as for API mode; **vision-capable models** recommended when using screenshot-based evaluation.

---

## Suggested site placements

1. **Hero or sub-hero** — “API + browser E2E for AI agents.”
2. **Features** — A **Browser mode** card with 3–4 bullets from the list above, plus a **Docs** or **Get started** link to your public developer documentation URL.
3. **How it works** — Simple 4-step diagram (observe → plan → act → evaluate).
4. **Docs CTA** — Same as above: one clear destination for install steps, YAML/configuration, evidence modes, and issue-triage CLI flags.

---

## Optional copy snippets

**Short:**  
*“Browser mode runs your AI product scenarios in a real browser with Playwright — same intelligent Replicant, plus visual goal checks when you need them.”*

**Medium:**  
*“ReplicantX now drives live web apps: the agent types, clicks, and navigates like a user, while goal evaluation can use the DOM, the LLM, or screenshots with vision models. Keep fast API tests for your backend; add browser mode for the full story.”*

---

*Document version: 2026-03-30. Align public claims with shipping behavior before publication.*
