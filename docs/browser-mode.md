# ReplicantX Browser Mode (Playwright) — Engineering Spec

## 1) Summary

Add a new `interaction_mode: browser` to Level 2 (`level: agent`) scenarios.

In browser mode, a Replicant:

1. **Authenticates** programmatically (Supabase admin magic-link → verify → app `/auth/refresh` to set httpOnly cookies)
2. Opens the app URL in **Playwright** (headless by default; headed optional)
3. Iterates up to `max_turns`:

   * Observes page state (DOM text + interactive controls)
   * Chooses an action (send chat, click card/button, fill field, wait, etc.)
   * Executes action
   * Evaluates progress (DOM and/or screenshot)
4. Produces artifacts (trace, screenshots) + enriched report

Key principle: keep the **existing Replicant configuration** (facts/goal/system_prompt/goal_evaluation/false positives) and introduce only additive fields for browser automation.

---

## 2) References we’re leaning on (implementation-critical)

* Playwright **APIRequestContext** can share cookies with the BrowserContext; responses with `Set-Cookie` update the BrowserContext automatically — ideal for your `/auth/refresh` cookie-setting flow. ([Playwright][1])
* Playwright tracing can be started/stopped per context and saved as `trace.zip`; traces are viewable using `playwright show-trace trace.zip`. ([Playwright][2])
* PydanticAI supports multimodal input using `BinaryContent` (perfect for screenshot-based goal evaluation). ([Pydantic AI][3])
* Supabase admin methods require the **service role** key and must be called on a trusted server-side environment (ReplicantX runner is fine). ([Supabase][4])

---

## 3) Desired behaviour

### 3.1 “Mostly chat + action cards”

Browser agent should:

* find a chat input (heuristics, no testids required)
* send message
* wait for UI response / loading to settle
* detect and click suggested buttons/cards that appear in or near the chat thread

### 3.2 Success evaluation

Support two evidence types:

1. **DOM evidence** (recommended default): visible text summary + URL + key UI state
2. **Screenshot evidence**: a page screenshot passed to the evaluator model via PydanticAI `BinaryContent` (only when configured / as fallback)

### 3.3 Turn loop

* Iterate until goal achieved OR max_turns reached
* Must avoid “stuck loops” (repeating same click / same chat message) via simple repetition detection

### 3.4 Non-blocking issue capture

* First-party browser issues such as `401`, `403`, `5xx`, console errors, and page errors should be recorded as diagnostics.
* These signals should **not** automatically stop the Replicant if the user flow is still progressing.
* A scenario may still pass while emitting an issue bundle or GitHub issue for a non-blocking bug.

---

## 4) Configuration changes (YAML + Pydantic models)

### 4.1 Add `interaction_mode` to `ReplicantConfig`

**Default** remains API mode, preserving current behaviour.

```yaml
replicant:
  interaction_mode: api   # api (default) | browser
```

### 4.2 Add `browser` block under `replicant`

```yaml
replicant:
  interaction_mode: browser
  browser:
    start_url: "https://app-qa.heyhelix.ai"
    headless: true
    browser_type: "chromium"          # future-proof
    viewport: { width: 1400, height: 900 }
    navigation_timeout_seconds: 30
    action_timeout_seconds: 15

    # Observation controls
    max_interactive_elements: 40
    max_visible_text_chars: 6000

    # Evidence for evaluation
    goal_evidence: "dom"              # dom | screenshot | dom_then_screenshot | both
    screenshot_on_each_turn: false    # default false (expensive)
    screenshot_on_failure: true

    # Safety (non-prod, but still)
    domain_allowlist:
      - "app-qa.heyhelix.ai"

    # Artifacts
    trace: "retain-on-failure"        # off | retain-on-failure | on
```

### 4.3 Extend `AuthProvider` for Supabase magic-link admin flow

Add a new provider:

* `supabase_magic_link` (your dev strategy)

```yaml
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated            # generated | fixed
  email: "gus+replicantx@yourdomain.com"   # required if user_mode: fixed
  redirect_to: "https://app-qa.heyhelix.ai"   # optional; depends on your app
  app_refresh_endpoint: "https://app-qa.heyhelix.ai/auth/refresh"
```

Notes:

* **generated** mode creates a unique email like `replicantx+<uuid>@replicantx.org` and injects it into `replicant.facts.email` automatically so the Replicant can use it if asked.
* This auth provider is used for **both** API mode (if you want later) and browser mode.

---

## 5) Architecture

### 5.1 New components (files / modules)

Add a browser toolkit under `replicantx/tools/`:

```
replicantx/
  tools/
    browser/
      playwright_manager.py
      observation.py
      actions.py
      chat_adapter.py
      artifacts.py
  auth/
    magic_link.py
  scenarios/
    browser_agent.py
```

### 5.2 Key interfaces

#### `BrowserAutomationDriver`

Responsible for launching Playwright, navigation, executing actions, and producing artifacts.

Core methods:

* `start() -> (context, page)`
* `stop()`
* `goto(url)`
* `perform(action: BrowserAction) -> BrowserActionResult`
* `capture_observation() -> BrowserObservation`
* `screenshot(path)`

#### `BrowserObservation`

A compact, LLM-friendly snapshot:

* `url`, `title`
* `visible_text` (sanitised, truncated)
* `interactive_elements: List[InteractiveElement]` (capped)

  * `id` (stable for the current turn)
  * `role` (button/link/textbox/menuitem…)
  * `name` (best-effort accessible name / innerText)
  * `locator_strategy` (driver-internal, not shown to LLM)

This supports the “element index/id” pattern so the model can click without guessing selectors.

#### `BrowserReplicantAgent` (tool-using planner)

A PydanticAI Agent with tools like:

* `send_chat(text)` — compose and submit in one step
* `compose_chat(text)` — type into the chat composer without submitting (for @mentions, autocomplete)
* `submit_chat()` — submit the current draft (prefers send button, falls back to Enter)
* `click(element_id)`
* `fill(element_id, text)`
* `press(key)`
* `wait(ms)` / `wait_for_text(text)`
* `scroll(direction, amount)`
* `navigate(url)` (restricted by allowlist)

The agent receives:

* goal + facts + system_prompt (existing)
* observation
* last N actions with outcomes (success/failure messages)

It chooses *one* tool call per turn.

---

## 6) Authentication implementation (your dev strategy)

### 6.1 New `SupabaseMagicLinkAuth` provider

**Inputs:**

* `project_url`
* `service_role_key`
* `user_mode` + `email` if fixed
* `app_refresh_endpoint` (Helix backend)
* optional `redirect_to`

**Flow (browser-context aware):**

1. Call Supabase admin generate-link to create (or fetch) a magic-link token for the user.
2. Verify token hash with `/auth/v1/verify` to obtain `access_token` + `refresh_token`.
3. Call `app_refresh_endpoint` using `browserContext.request` so `Set-Cookie` updates the browser context cookie jar. ([Playwright][1])
4. Navigate to `start_url` and assert “logged-in enough”:

   * Heuristic: presence of a known logged-in-only text/button (configurable later)
   * If not detected, fail early with auth error and save screenshot/trace.

Security note: service role keys are admin-level and must never ship client-side; runner usage is correct. ([Supabase][4])

---

## 7) Observation extraction (no `data-testid` required)

### 7.1 Visible text summary

Goal: provide enough context without dumping full HTML.

Implementation approach:

* Prefer: `page.inner_text("body")` (or evaluate JS to get visible text)
* Strip repeated whitespace
* Truncate to `max_visible_text_chars`
* Optionally remove navbar/footer blocks by heuristics (later)

### 7.2 Interactive element harvesting

Goal: a shortlist of things the Replicant can click.

Approach (best-effort):

* Query for common interactables:

  * `button`, `a[href]`, `input`, `textarea`, `[role=button]`, `[role=link]`, `[role=menuitem]`
* Filter:

  * visible, enabled
  * has meaningful name: aria-label OR innerText OR placeholder
* For each element, store:

  * role guess
  * name
  * a Playwright locator strategy (internal)
* Sort:

  1. elements near chat area (if detected),
  2. elements with “primary” semantics (button > link),
  3. newest appearing (optional later)

### 7.3 Optional “Helix chat adapter” (v2, not required for v1)

Since you *can* add testids later, keep an optional config block:

```yaml
replicant:
  browser:
    ui:
      chat_input: "[data-testid='chat-input']"
      chat_send: "[data-testid='chat-send']"
      chat_thread: "[data-testid='chat-thread']"
```

If provided, the agent becomes extremely reliable. If absent, fall back to heuristics.

---

## 8) Action execution rules

### 8.1 Stability rules (to reduce flakiness)

After each action:

* wait for one of:

  * network idle (if applicable)
  * a short debounce (e.g. 250–500ms)
  * a “new content appeared” heuristic (text length changed, new button appeared)
* use action timeout `action_timeout_seconds`

### 8.2 Anti-loop detection

Track the last ~6 actions; if the same action repeats 3 times with no visible text change, fail with “stuck loop”.

---

## 9) Goal evaluation (DOM + screenshot options)

Extend goal evaluation to accept “evidence”.

### 9.1 Evidence modes

* `dom`: evaluator gets (goal, facts, last turns, DOM summary)
* `screenshot`: evaluator gets (goal, facts, screenshot BinaryContent)
* `dom_then_screenshot`: try DOM first; if low confidence, fall back to screenshot
* `both`: always provide both (more expensive)

Screenshot evaluation uses PydanticAI multimodal input (`BinaryContent`) so we can feed the screenshot bytes directly. ([Pydantic AI][3])

### 9.2 False positives

Keep your existing pattern: custom `goal_evaluation_prompt` supports explicit false positive rules (e.g., “agent said it will book” ≠ booked; must see “confirmed” screen / ref number / etc.).

---

## 10) Reporting & artifacts

### 10.1 Playwright trace

If enabled:

* `context.tracing.start(screenshots=True, snapshots=True, sources=True)`
* stop + save `trace.zip` on failure (or always)
  Traces are viewable via `playwright show-trace trace.zip`. ([Playwright][2])

### 10.2 Screenshots

* Always screenshot on failure
* Optional screenshot each turn

### 10.3 Report structure changes

Update `StepResult` to add optional browser fields (backwards-compatible defaults):

* `action_type`, `action_summary`
* `page_url`
* `observation_excerpt`
* `artifact_paths` (screenshot, trace)

If you want to avoid changing the model, map:

* `user_message` = action summary
* `response` = observation excerpt
  …but I’d recommend proper fields since you’ll use this constantly.

---

## 11) CLI changes

Current CLI flags for standalone issue processing:

* `--issue-mode {off,auto-high-confidence,draft-only}`
* `--issue-repo owner/name`
* `--issue-artifact-upload {on,off}`
* `--issue-output DIR`

Current browser runtime settings remain YAML-configured:

* `browser.headless`
* `browser.trace`
* `browser.screenshot_on_each_turn`
* `browser.navigation_timeout_seconds`
* `browser.action_timeout_seconds`

Keep current execution model. You’re running one at a time now, so no special concurrency work required.

---

## 12) Implementation plan (deliverable-driven)

### Phase 1 (MVP): Browser mode + auth + DOM evaluation

**Deliverables**

* `interaction_mode: browser`
* `SupabaseMagicLinkAuth`
* Playwright driver + observation + tool-using planner
* DOM-based evaluation
* screenshot on failure
* trace on failure

**Acceptance test**

* “Open Helix QA, send chat message, click a suggested card, reach a success/confirmation UI state or hit max_turns with a clear report.”

### Phase 2: Screenshot evaluation + better chat heuristics

* Add screenshot evaluation modes (`dom_then_screenshot`, `both`)
* Improve chat input detection
* Improve element ranking for cards/buttons in chat thread

### Phase 3: Optional Helix UI adapter (testids) + hybrid mode

* If you decide to add `data-testid`, wire `chat_thread` parsing for reliable “assistant said X” extraction.
* Add `interaction_mode: hybrid` later (API calls + UI in one scenario).

---

## 13) Example scenarios

### 13.1 Browser mode, generated user, DOM-first eval

```yaml
name: "Helix QA - chat + card flow (browser)"
level: agent
base_url: "https://app-qa.heyhelix.ai"   # keep required; treat as app base in browser mode
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated
  app_refresh_endpoint: "https://app-qa.heyhelix.ai/auth/refresh"

replicant:
  interaction_mode: browser
  goal: "Get to a clear confirmation screen that a trip request was created."
  facts:
    name: "ReplicantX Test User"
    origin: "London"
    destination: "Paris"
  system_prompt: |
    You are a user of Helix trying to accomplish the goal.
    Prefer using chat, but click suggested buttons/cards when they help.
    If stuck, try a different approach.
  initial_message: "Hi — I need to book a flight from London to Paris next week."  # optional
  max_turns: 20
  goal_evaluation_mode: hybrid
  browser:
    start_url: "https://app-qa.heyhelix.ai"
    headless: true
    goal_evidence: dom
    trace: retain-on-failure
    screenshot_on_failure: true
```

### 13.2 DOM then screenshot fallback

```yaml
replicant:
  goal_evaluation_mode: intelligent
  browser:
    goal_evidence: dom_then_screenshot
```

---

## 14) Small recommendations (pragmatic)

* Even if you “try without testids first”, add a **single** optional selector override mechanism (like the `ui.chat_input` example). It lets you harden Helix later without rewriting ReplicantX.
* Default to **DOM-first evaluation**, screenshot only when needed (cost + speed).
* Make the agent action space *small and typed* (tool calls), not “write Playwright code”.

