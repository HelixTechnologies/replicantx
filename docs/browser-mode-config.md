# Browser Mode Configuration Guide

## Overview

Browser mode allows ReplicantX to test web applications using Playwright browser automation. The agent can interact with web pages naturally through chat, clicking buttons, and filling forms.

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
  initial_message: "Hi, I'd like to book a flight."
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
