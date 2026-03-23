# Browser Mode Configuration Guide

## Overview

Browser mode allows ReplicantX to test web applications using Playwright browser automation. The agent can interact with web pages naturally through chat, clicking buttons, and filling forms.

It also supports standalone browser issue triage from the CLI:
- capture structured issue bundles for failed or suspicious browser runs
- optionally enrich them with Logfire excerpts
- optionally auto-file high-confidence GitHub issues
- continue the Replicant flow when non-blocking app errors occur and the goal is still achievable

## Complete Configuration Example

```yaml
name: "Browser Mode Test"
level: agent
base_url: "https://app.example.com"  # Used for reference only in browser mode
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated  # or "fixed"
  email: "user@example.com"  # required if user_mode: fixed
  app_refresh_endpoint: "https://app.example.com/auth/refresh"

replicant:
  interaction_mode: browser  # Enable browser mode

  # Agent configuration
  goal: "Complete a flight booking"
  facts:
    name: "John Doe"
    origin: "London"
    destination: "Paris"
  system_prompt: |
    You are a user trying to accomplish your goal.
  initial_message: "Hi, I'd like to book a flight."  # optional — planner derives from goal/facts if omitted
  max_turns: 20
  completion_keywords:
    - "booked"
    - "confirmed"
    - "complete"

  # LLM configuration for response generation
  llm:
    model: "openai:gpt-4.1-mini"  # Main model for generating responses
    temperature: 0.7
    max_tokens: 150

  # Goal evaluation configuration
  goal_evaluation_mode: intelligent  # keywords | intelligent | hybrid
  goal_evaluation_model: "openai:gpt-4.1-mini"  # Model for DOM evaluation

  # Browser-specific configuration
  browser:
    # Browser settings
    start_url: "https://app.example.com"
    headless: true  # or false for headed mode
    browser_type: "chromium"  # chromium | firefox | webkit
    viewport:
      width: 1400
      height: 900
    navigation_timeout_seconds: 30
    action_timeout_seconds: 15

    # Observation controls
    max_interactive_elements: 40  # Max elements to extract per page
    max_visible_text_chars: 6000  # Max text to extract

    # Evidence mode for goal evaluation
    goal_evidence: dom_then_screenshot  # dom | screenshot | dom_then_screenshot | both

    # Screenshot evaluation model (optional, for vision-capable model)
    screenshot_evaluation_model: "openai:gpt-4o"  # Use GPT-4o for screenshots

    # Screenshot capture settings
    screenshot_on_each_turn: false  # Capture every turn (expensive)
    screenshot_on_failure: true  # Always capture on failure

    # Safety
    domain_allowlist:
      - "app.example.com"
      - "*.example.com"

    # Artifacts
    trace: retain-on-failure  # off | retain-on-failure | on
```

## Configuration Options

### Interaction Mode
- `api` (default) - HTTP API mode
- `browser` - Playwright browser automation

## Standalone Issue Triage and GitHub Autofiling

Issue processing is controlled from the CLI, not the YAML scenario. Existing browser scenarios work as-is.

### CLI Options

```bash
replicantx run tests/browser_test.yaml \
  --issue-mode draft-only \
  --issue-artifact-upload off \
  --issue-output artifacts/issues
```

```bash
replicantx run tests/browser_test.yaml \
  --issue-mode auto-high-confidence \
  --issue-repo HelixTechnologies/helix-agent
```

```bash
replicantx run tests/browser_test.yaml \
  --issue-mode draft-only \
  --logfire-config replicantx.logfire.yaml
```

Available options:
- `--issue-mode off|auto-high-confidence|draft-only`
- `--issue-repo owner/name`
- `--issue-artifact-upload on|off`
- `--issue-output <dir>`
- `--logfire-config <path>`

### How Issue Processing Behaves

- Browser runs always continue if the Replicant can keep making progress.
- First-party `401`, `403`, `500`, console errors, and page errors are recorded as diagnostics rather than immediately stopping the run.
- A scenario can pass and still produce an issue bundle or GitHub issue if the bug did not block the user flow.

Classifier decisions:
- `auto_file`: high-confidence app bug
- `review`: suspicious but ambiguous
- `skip`: likely automation or Playwright limitation

What happens for each decision:
- `auto_file`: writes local bundle and, in `auto-high-confidence` mode, creates or updates a GitHub issue
- `review`: writes local bundle and markdown draft only
- `skip`: writes local bundle for reference only; no GitHub issue

### Output Files

Issue artifacts are written under `--issue-output/<scenario-slug>/`:
- `issue_bundle.json`: structured diagnostics, classification, artifacts, issue body, and Logfire excerpt
- `issue.md`: rendered GitHub issue markdown draft

Browser traces and screenshots remain in the scenario artifact directory and are linked from the bundle.

### Environment Variables

```bash
# GitHub filing
REPLICANTX_GITHUB_TOKEN=github_pat_or_app_token

# Logfire enrichment
REPLICANTX_LOGFIRE_API_KEY=your-logfire-read-token
REPLICANTX_LOGFIRE_BASE_URL=https://logfire-api.pydantic.dev  # optional
REPLICANTX_LOGFIRE_SERVICE_NAME=helix-api                     # optional
REPLICANTX_LOGFIRE_CONFIG=replicantx.logfire.yaml            # optional

# Supabase artifact upload
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
REPLICANTX_ARTIFACT_BUCKET=replicantx-artifacts               # optional
REPLICANTX_ARTIFACT_SIGNED_URL_TTL_SECONDS=604800             # optional

# Optional label included in issue bundles/issues
REPLICANTX_ENVIRONMENT=staging
```

Notes:
- If you want purely local issue drafts, use `--issue-artifact-upload off`.
- Artifact uploads use private Supabase Storage with signed URLs.
- GitHub issue dedupe is based on a deterministic fingerprint embedded in the issue body.
- Logfire query config is auto-discovered from `replicantx.logfire.yaml` or `replicantx.logfire.yml` if present.

### Configurable Logfire Query

Different products often use different Logfire attribute names. ReplicantX supports a repo-specific YAML query definition instead of hardcoding those mappings in Python.

Example `replicantx.logfire.yaml`:

```yaml
service_name: product-api
static_filters:
  - "service_name = {service_name}"
  - "attributes->>'tenant' = 'acme'"
correlation_joiner: and
correlation_rules:
  - identity_field: user_id
    expressions:
      - "attributes->>'actor_id' = {value}"
      - "attributes->>'user_id' = {value}"
    combine_with: or
  - identity_field: conversation_id
    expressions:
      - "attributes->>'session_key' = {value}"
time_window:
  before_seconds: 30
  after_seconds: 45
limit: 10
```

Supported placeholders:
- `{value}`
- `{service_name}`
- `{environment}`
- `{user_id}`
- `{conversation_id}`

See [../replicantx.logfire.example.yaml](../replicantx.logfire.example.yaml) for a ready-to-copy example.

### Goal Evidence Modes

| Mode | Description | Speed | Accuracy | Use Case |
|------|-------------|-------|----------|----------|
| `dom` | Text/DOM only | ⚡⚡⚡ Fastest | Good | Text-heavy apps, speed-critical |
| `screenshot` | Visual analysis | 🐢 Slowest | Excellent | Visual-heavy apps, complex UIs |
| `dom_then_screenshot` | Smart hybrid | ⚡⚡ Fast | Very Good | **Production use (recommended)** |
| `both` | Combined | ⚡ Moderate | Excellent | Critical flows, debugging |

### Model Selection Strategy

#### Option 1: Fast/Cheap (Single Small Model)
```yaml
replicant:
  llm:
    model: "openai:gpt-4.1-mini"
  goal_evaluation_model: "openai:gpt-4.1-mini"
  browser:
    goal_evidence: dom
    screenshot_evaluation_model: "openai:gpt-4.1-mini"
```

#### Option 2: Balanced (Tiered Models) - Recommended
```yaml
replicant:
  llm:
    model: "openai:gpt-4.1-mini"  # Fast for responses
  goal_evaluation_model: "openai:gpt-4.1-mini"  # Fast for DOM
  browser:
    goal_evidence: dom_then_screenshot  # Smart fallback
    screenshot_evaluation_model: "openai:gpt-4o"  # Vision for screenshots
```

#### Option 3: Maximum Accuracy (Large Vision Model)
```yaml
replicant:
  llm:
    model: "openai:gpt-4o"
  goal_evaluation_model: "openai:gpt-4o"
  browser:
    goal_evidence: both
    screenshot_evaluation_model: "openai:gpt-4o"
    screenshot_on_each_turn: true
```

### Screenshot Evaluation Models

Use vision-capable models for `screenshot_evaluation_model`:

**Recommended:**
- `openai:gpt-5.2` - Excellent vision, fast
- `anthropic:claude-4-6-sonnet-latest` - Great visual understanding

**Budget-friendly:**
- `openai:gpt-4.1-mini` - Decent vision, very fast
- `openai:gpt-4.1-nano` - Minimal vision capability

### Trace Modes

| Mode | Description |
|------|-------------|
| `off` | No tracing (fastest) |
| `retain-on-failure` | Keep trace only on failure (default) |
| `on` | Always keep traces (for debugging) |

View traces with: `playwright show-trace trace.zip`

### Authentication

#### Supabase Magic Link (Recommended for Testing)
```yaml
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated  # Auto-generates unique email
  app_refresh_endpoint: "https://app.example.com/auth/refresh"
```

#### Fixed User
```yaml
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: fixed
  email: "test@example.com"
  app_refresh_endpoint: "https://app.example.com/auth/refresh"
```

## Cost Optimization

### Reduce Costs with Smart Configuration

1. **Use `dom_then_screenshot`** - Only uses expensive vision model when needed
2. **Disable `screenshot_on_each_turn`** - Capture only for evaluation
3. **Use tiered models** - Small for DOM, large for screenshots only
4. **Set reasonable timeouts** - Avoid long-running screenshot captures

### Cost Comparison (per 100 evaluations)

| Configuration | Est. Cost (USD) |
|--------------|-----------------|
| DOM-only with gpt-4.1-mini | ~$0.10 |
| DOM-then-screenshot with gpt-4.1-mini/gpt-5.2 | ~$0.50 |
| Screenshot-only with gpt-5.2 | ~$2.00 |
| Both modes with gpt-5.2 | ~$3.00 |

*Estimates based on typical usage patterns*

## Best Practices

1. **Start with DOM-only** - Fast and cheap, add screenshots if needed
2. **Use `dom_then_screenshot`** in production - Best balance
3. **Set `screenshot_on_failure: true`** - Essential for debugging
4. **Use `trace: retain-on-failure`** - Helps investigate failures
5. **Keep `headless: true`** in CI/CD, use `false` locally for debugging
6. **Use `domain_allowlist`** - Prevent navigation to unexpected sites
7. **Use `draft-only` first** - Validate your classifier output locally before enabling GitHub autofiling
8. **Turn artifact upload off for local-only work** - Use `--issue-artifact-upload off` when you do not need signed URLs

## Example Use Cases

### E-commerce Flow
```yaml
goal: "Add item to cart and proceed to checkout"
browser:
  goal_evidence: dom_then_screenshot
  screenshot_evaluation_model: "openai:gpt-4o"
```

### Form Submission
```yaml
goal: "Complete user registration form"
browser:
  goal_evidence: dom  # Text confirmation is sufficient
```

### Dashboard Navigation
```yaml
goal: "Navigate to settings page and update profile"
browser:
  goal_evidence: both  # Need visual confirmation
  screenshot_on_each_turn: true
```
