# ReplicantX

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

**ReplicantX** is an end-to-end testing harness for AI agents that communicates via web service APIs. It enables you to run comprehensive test scenarios against live HTTP APIs with support for multiple authentication methods, browser automation, and detailed reporting.

## ✨ Features

- **Two Interaction Modes**:
  - **API Mode**: Test HTTP APIs directly with structured requests/responses
  - **Browser Mode** 🆕: Automate web applications using Playwright with intelligent visual goal evaluation
- **Two Test Levels**:
  - **Level 1 (Basic)**: Fixed user messages with deterministic assertions
  - **Level 2 (Agent)**: Intelligent Replicant agent with configurable facts and conversation goals
- **Pydantic-Based Replicant Agent**: Smart conversational agent that acts like a real user
- **Configurable Facts & Behavior**: Agents can have knowledge (Name, Preferences) and custom personalities
- **Screenshot-Based Goal Evaluation**: Multimodal LLM evaluation with vision models for accurate UI state detection
- **Smart Element Ranking**: Chat-aware element prioritization for natural web interaction
- **Real-time Monitoring**: Watch mode (`--watch`) for live conversation monitoring
- **Technical Debugging**: Debug mode (`--debug`) with detailed HTTP, validation, and AI processing logs
- **Multiple Authentication**: Supabase email/password, Supabase magic link, custom JWT, or no-auth
- **CLI Interface**: Easy-to-use command-line interface with `replicantx run`
- **Parallel Execution**: Run multiple test scenarios concurrently for faster execution
- **Automatic .env Loading**: No manual environment variable sourcing required
- **GitHub Actions Ready**: Built-in workflow for PR testing with Render preview URLs
- **Rich Reporting**: Markdown and JSON reports with timing and assertion results
- **Standalone Issue Triage**: Write browser issue bundles locally and optionally auto-file high-confidence GitHub issues from the CLI
- **Playwright Tracing**: Capture browser traces for debugging with `playwright show-trace`
- **Retry & Backoff**: Robust HTTP client with automatic retry logic

## 🚀 Quick Start

### Installation

```bash
# Basic installation (for API mode)
pip install replicantx[cli]

# For browser mode (includes Playwright)
pip install replicantx[cli]

# Install Playwright browsers (one-time setup for browser mode)
playwright install
```

### Basic Usage

1. Create a test scenario YAML file:

**Basic Scenario (Level 1):**
```yaml
# tests/basic_test.yaml
name: "Test AI Agent Conversation"
base_url: https://your-api.com/api/chat
auth:
  provider: noop  # or supabase, jwt
level: basic
steps:
  - user: "Hello, I need help with booking a flight"
    expect_contains: ["flight", "booking"]
  - user: "I want to go to Paris"
    expect_regex: "(?i)paris.*available"
```

**Agent Scenario (Level 2):**

*Generic Customer Support Example:*
```yaml
# tests/support_test.yaml
name: "Customer Support - Account Issue"
base_url: https://your-api.com/api/support
auth:
  provider: noop
level: agent
replicant:
  goal: "Get help with account access issue"
  facts:
    name: "Alex Chen"
    email: "alex.chen@example.com"
    account_id: "ACC-123456"
    issue_type: "login_problem"
    last_login: "2 weeks ago"
  system_prompt: |
    You are a customer seeking help with an account issue. You have the 
    necessary information but don't provide all details upfront.
    Answer questions based on your available facts.
  initial_message: "Hi, I'm having trouble accessing my account."
  max_turns: 12
  completion_keywords: ["resolved", "ticket created", "issue fixed"]
```

*Travel Booking Example:*
```yaml
# tests/travel_test.yaml
name: "Travel Booking - Flight Reservation"
base_url: https://your-api.com/api/chat
auth:
  provider: noop
level: agent
replicant:
  goal: "Book a business class flight to Paris"
  facts:
    name: "Sarah Johnson"
    email: "sarah@example.com"
    travel_class: "business"
    destination: "Paris"
    budget: "$2000"
  system_prompt: |
    You are a customer trying to book a flight. You have the 
    necessary information but don't provide all details upfront.
    Answer questions based on your available facts.
  initial_message: "Hi, I'd like to book a flight to Paris."
  max_turns: 15
  completion_keywords: ["booked", "confirmed", "reservation number"]
```

2. Run the test:

```bash
replicantx run tests/my_test.yaml --report report.md
```

3. View the generated report in `report.md`

### 🌐 Browser Mode (Playwright Automation)

**NEW:** Browser mode enables end-to-end testing of web applications using Playwright automation. The Replicant agent can interact with web pages naturally through chat, clicking buttons, and filling forms, with intelligent visual goal evaluation.

#### Key Features

- **Playwright Automation**: Control Chromium, Firefox, or WebKit browsers
- **Multimodal Goal Evaluation**: Screenshot-based evaluation using vision models (GPT-4o, Claude, etc.)
- **Smart Chat Detection**: Heuristics to find chat inputs without testids
- **Intelligent Element Ranking**: Prioritizes elements near chat thread
- **Flexible Evidence Modes**: DOM, screenshot, or hybrid evaluation strategies
- **Supabase Magic Link Auth**: Auto-generates users for testing
- **Browser Tracing**: Capture traces for debugging with `playwright show-trace`

#### Quick Example

```yaml
# tests/browser_test.yaml
name: "Browser Mode - Flight Booking"
level: agent
base_url: "https://app.example.com"  # Reference only in browser mode
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated  # Auto-generates unique email
  app_refresh_endpoint: "https://app.example.com/auth/refresh"

replicant:
  interaction_mode: browser  # Enable browser mode
  goal: "Complete a flight booking from London to Paris"
  facts:
    name: "Test User"
    origin: "London"
    destination: "Paris"
  system_prompt: |
    You are a user trying to book a flight.
    Use chat, but click suggested buttons when they help.
  initial_message: "Hi, I'd like to book a flight from London to Paris next week."

  # Main LLM for response generation (smaller, faster)
  llm:
    model: "openai:gpt-4.1-mini"

  browser:
    start_url: "https://app.example.com"
    headless: true

    # Smart evaluation: DOM first, screenshot fallback if unsure
    goal_evidence: dom_then_screenshot

    # Use vision model for screenshots (better visual understanding)
    screenshot_evaluation_model: "openai:gpt-5.2"

    # Capture artifacts for debugging
    screenshot_on_failure: true
    trace: retain-on-failure
```

#### Installation with Browser Support

```bash
# Install with Playwright
pip install replicantx[cli]

# Install Playwright browsers (one-time)
playwright install
```

#### Running Browser Mode Tests

```bash
# Run with watch mode (see live browser interaction)
replicantx run tests/browser_test.yaml --watch

# Run with debug mode (see technical details)
replicantx run tests/browser_test.yaml --debug

# Watch the actual browser window
# set replicant.browser.headless: false in the YAML, then run:
replicantx run tests/browser_test.yaml --watch
```

#### Browser Issue Triage and GitHub Autofiling

ReplicantX can now capture browser issues during standalone CLI runs without relying on GitHub Actions.

Important behavior:
- A first-party `401`, `500`, console error, or page error does **not** automatically stop the Replicant.
- If the browser flow is still progressing, the Replicant continues trying to complete the goal.
- A scenario can therefore **pass** and still produce an issue bundle or GitHub issue for a non-blocking bug.

No scenario YAML changes are required for this. Enable it from the CLI:

```bash
# Local draft only: write issue.md + issue_bundle.json, do not file GitHub issues
replicantx run tests/browser_test.yaml \
  --issue-mode draft-only \
  --issue-artifact-upload off \
  --issue-output artifacts/issues

# Auto-file high-confidence issues directly to GitHub
replicantx run tests/browser_test.yaml \
  --issue-mode auto-high-confidence \
  --issue-repo HelixTechnologies/helix-agent

# Use a repo-specific Logfire query definition
replicantx run tests/browser_test.yaml \
  --issue-mode draft-only \
  --logfire-config replicantx.logfire.yaml
```

Issue handling modes:
- `off`: do not run issue processing
- `draft-only`: write local issue drafts and bundles only
- `auto-high-confidence`: auto-file `auto_file` issues and keep local bundles for everything processed

What gets written to `--issue-output`:
- `issue_bundle.json`: structured diagnostics, classification, artifacts, and Logfire excerpt
- `issue.md`: rendered GitHub issue body draft
- Browser artifacts remain in the normal scenario artifact directory and are linked from the bundle

Classifier outcomes:
- `auto_file`: high-confidence app bug, eligible for GitHub filing in `auto-high-confidence` mode
- `review`: suspicious or ambiguous issue, bundle written locally but no GitHub issue created
- `skip`: likely automation/control limitation, bundle written locally for reference but no GitHub issue created

Integration environment variables:

```bash
# GitHub issue creation
REPLICANTX_GITHUB_TOKEN=github_pat_or_app_token

# Logfire enrichment
REPLICANTX_LOGFIRE_API_KEY=your-logfire-read-token
REPLICANTX_LOGFIRE_BASE_URL=https://logfire-api.pydantic.dev   # optional
REPLICANTX_LOGFIRE_SERVICE_NAME=helix-api                      # optional
REPLICANTX_LOGFIRE_CONFIG=replicantx.logfire.yaml             # optional

# Artifact uploads (private Supabase Storage + signed URLs)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
REPLICANTX_ARTIFACT_BUCKET=replicantx-artifacts                # optional
REPLICANTX_ARTIFACT_SIGNED_URL_TTL_SECONDS=604800              # optional

# Optional execution label used in bundles/issues
REPLICANTX_ENVIRONMENT=staging
```

Notes:
- If you want completely local drafts with no artifact upload, use `--issue-artifact-upload off`.
- Artifact upload is useful for GitHub issues because the issue body can include signed links to the relevant screenshots and traces only.
- `--issue-repo` must be in `owner/name` format.
- Logfire query config is auto-discovered from `replicantx.logfire.yaml` or `replicantx.logfire.yml` if present.

#### Configurable Logfire Query

The Logfire query is now configurable so different products can map ReplicantX’s extracted browser identities onto their own Logfire record structure.

Default lookup order:
- `--logfire-config <path>`
- `REPLICANTX_LOGFIRE_CONFIG`
- `replicantx.logfire.yaml`
- `replicantx.logfire.yml`
- built-in default query

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

Supported placeholders inside query fragments:
- `{value}`: current identity value for a correlation rule
- `{service_name}`: configured service name
- `{environment}`: execution environment label when available
- `{user_id}` and `{conversation_id}`: extracted browser identity values

See [replicantx.logfire.example.yaml](replicantx.logfire.example.yaml) for a working starting point.

#### Environment Variables

```bash
# Supabase Magic Link Authentication
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key  # Admin key for magic links

# LLM API Keys (for Replicant agent)
OPENAI_API_KEY=sk-your-openai-key  # For gpt-4.1-mini, gpt-5.2, etc.
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key  # For Claude models

# App Configuration
APP_START_URL=https://app-qa.example.com  # Override start_url
```

#### Configuration Options

**Evidence Modes** (`browser.goal_evidence`):

| Mode | Description | Speed | Accuracy |
|------|-------------|-------|----------|
| `dom` | Text/DOM only | ⚡⚡⚡ Fastest | Good |
| `screenshot` | Visual analysis | 🐢 Slowest | Excellent |
| `dom_then_screenshot` | Smart hybrid | ⚡⚡ Fast | Very Good |
| `both` | Combined | ⚡ Moderate | Excellent |

**Model Selection**:

```yaml
replicant:
  # Tiered models for cost optimization
  llm:
    model: "openai:gpt-4.1-mini"  # Fast for responses

  goal_evaluation_model: "openai:gpt-4.1-mini"  # Fast for DOM

  browser:
    screenshot_evaluation_model: "openai:gpt-5.2"  # Vision for screenshots
```

#### For Complete Documentation

📖 **See [docs/browser-mode-config.md](docs/browser-mode-config.md)** for:
- Complete configuration reference
- Model selection strategies
- Cost optimization tips
- Trace debugging guide
- Standalone issue reporting and GitHub autofiling
- Best practices and examples

### 🔐 Environment Variables & Configuration

ReplicantX **automatically detects environment variables** from your system, `.env` files, and CI/CD environments. No special configuration needed when installed as a dependency!

#### ✅ **Automatic Detection**

**When you install ReplicantX in your project:**
```bash
# Your project setup
pip install replicantx[cli]

# Your environment variables (any of these methods work)
export OPENAI_API_KEY=sk-your-key          # Shell environment
echo "OPENAI_API_KEY=sk-key" > .env        # .env file
# OR set in your CI/CD platform

# ReplicantX automatically finds them!
replicantx run tests/*.yaml
```

#### 🚀 **Quick Setup**

**Essential variables for different use cases:**

```bash
# LLM Integration (PydanticAI auto-detects these)
export OPENAI_API_KEY=sk-your-openai-key
export ANTHROPIC_API_KEY=sk-ant-your-anthropic-key

# Supabase Authentication
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_ANON_KEY=your-supabase-anon-key

# Supabase Service Role Key (for browser mode magic link auth)
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Browser issue triage / autofiling
export REPLICANTX_GITHUB_TOKEN=github_pat_or_app_token
export REPLICANTX_LOGFIRE_API_KEY=your-logfire-read-token
export REPLICANTX_LOGFIRE_CONFIG=replicantx.logfire.yaml

# Target API Configuration
export REPLICANTX_TARGET=your-api-domain.com

# Custom Authentication
export JWT_TOKEN=your-jwt-token
export MY_API_KEY=your-custom-api-key
```

#### 🔄 **Works Everywhere**

**Local Development:**
```bash
# Create .env file (ReplicantX automatically loads it!)
cat > .env << 'EOF'
OPENAI_API_KEY=sk-dev-key
REPLICANTX_TARGET=dev-api.example.com
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key  # For browser mode
REPLICANTX_GITHUB_TOKEN=github_pat_or_app_token  # For CLI GitHub issue filing
REPLICANTX_LOGFIRE_API_KEY=your-logfire-read-token
REPLICANTX_LOGFIRE_CONFIG=replicantx.logfire.yaml
EOF

# Just run tests - no need to source .env!
replicantx run tests/*.yaml

# Or export manually (old way still works)
export OPENAI_API_KEY=sk-dev-key
replicantx run tests/*.yaml
```

**GitHub Actions (No .env files needed!):**
```yaml
# .github/workflows/test-api.yml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      # GitHub Secrets → Environment Variables
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      REPLICANTX_TARGET: ${{ secrets.API_TARGET_URL }}
    steps:
      - run: pip install replicantx[cli]
      - run: replicantx run tests/*.yaml --ci
      # ReplicantX automatically finds the variables!
```

#### 📝 **Using in YAML Files**

Reference variables with `{{ env.VARIABLE_NAME }}` syntax:

```yaml
name: "API Test"
base_url: "https://{{ env.REPLICANTX_TARGET }}/api/chat"
auth:
  provider: supabase
  project_url: "{{ env.SUPABASE_URL }}"
  api_key: "{{ env.SUPABASE_ANON_KEY }}"
level: agent
replicant:
  facts:
    api_key: "{{ env.MY_API_KEY }}"
  llm:
    model: "openai:gpt-4o"  # Uses OPENAI_API_KEY automatically
```

#### 🎯 **GitHub Secrets Setup**

1. **Go to** Repository Settings → Secrets and Variables → Actions
2. **Add secrets:**
   - `OPENAI_API_KEY` = `sk-your-openai-key`
   - `SUPABASE_URL` = `https://your-project.supabase.co`
   - `SUPABASE_ANON_KEY` = `your-supabase-anon-key`
   - `SUPABASE_SERVICE_ROLE_KEY` = `your-service-role-key` (for browser mode)
   - `REPLICANTX_TARGET` = `api.yourproject.com`

3. **Use in workflow:**
   ```yaml
   env:
     OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
     REPLICANTX_TARGET: ${{ secrets.REPLICANTX_TARGET }}
   ```

**💡 Key Benefits:**
- ✅ **Automatic .env loading** - Just create a .env file and run tests
- ✅ **Zero configuration** - ReplicantX finds variables automatically
- ✅ **Works everywhere** - local, CI/CD, Docker, cloud platforms
- ✅ **Secure by default** - no hardcoded secrets in code
- ✅ **Standard patterns** - uses industry-standard environment variable detection

> **Note**: Create a `.env.example` file in your project to document which variables are needed. See our comprehensive environment variable guide in the [LLM Integration](#-environment-variables) section.

## 🎯 **Automatic .env File Loading**

ReplicantX automatically loads environment variables from `.env` files using python-dotenv. **No manual sourcing required!**

### 📁 **Create .env File**

```bash
# Create .env file in your project root
cat > .env << 'EOF'
# LLM API Keys
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key

# Target API
REPLICANTX_TARGET=https://api.yourproject.com

# Supabase Authentication
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key  # For browser mode magic link auth
TEST_USER_EMAIL=test@example.com
TEST_USER_PASSWORD=testpassword123

# JWT Authentication
JWT_TOKEN=your-jwt-token
EOF
```

### 🚀 **Run Tests Directly**

```bash
# Just run - ReplicantX finds .env automatically!
replicantx run tests/*.yaml

# Validate test files
replicantx validate tests/*.yaml

# Generate reports
replicantx run tests/*.yaml --report report.md
```

### 🔍 **How It Works**

1. **Automatic Discovery**: ReplicantX looks for `.env` files in current directory and parent directories
2. **Non-intrusive**: If no `.env` file exists, it continues normally
3. **Environment Priority**: Existing environment variables take precedence over `.env` values
4. **Secure**: `.env` files should be added to `.gitignore` to avoid committing secrets

### 🛡️ **Security Best Practices**

```bash
# Add .env to .gitignore
echo ".env" >> .gitignore

# Create .env.example for documentation
cat > .env.example << 'EOF'
# Copy this file to .env and fill in your values
OPENAI_API_KEY=sk-your-openai-key-here
REPLICANTX_TARGET=https://your-api-domain.com
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here  # For browser mode
REPLICANTX_GITHUB_TOKEN=github_pat_or_app_token       # For issue autofiling
REPLICANTX_LOGFIRE_API_KEY=your-logfire-read-token
REPLICANTX_LOGFIRE_CONFIG=replicantx.logfire.yaml
EOF
```

**✅ No more manual environment variable management!**

## 📖 Documentation

### Test Scenario Configuration

#### Basic Scenarios (Level 1)

Basic scenarios use fixed user messages with deterministic assertions:

```yaml
name: "Basic Test Scenario"
base_url: "https://api.example.com/chat"
auth:
  provider: noop
level: basic
steps:
  - user: "User message"
    expect_contains: ["expected", "text"]
    expect_regex: "regex_pattern"
    expect_equals: "exact_match"
    expect_not_contains: ["forbidden", "text"]
```

#### Agent Scenarios (Level 2)

Agent scenarios use intelligent Replicant agents that converse naturally:

```yaml
name: "Agent Test Scenario"
base_url: "https://api.example.com/chat"
auth:
  provider: supabase
  email: test@example.com
  password: password123
  project_url: "{{ env.SUPABASE_URL }}"
  api_key: "{{ env.SUPABASE_ANON_KEY }}"
level: agent
validate_politeness: false  # Optional: validate conversational tone (default: false)
replicant:
  goal: "Description of what the agent should achieve"
  facts:
    name: "User Name"
    email: "user@example.com"
    # Add any facts the agent should know
  system_prompt: |
    Customize the agent's personality and behavior.
    This prompt defines how the agent should act.
  initial_message: "Starting message for the conversation"
  max_turns: 20
  completion_keywords: 
    - "success"
    - "completed"
    - "finished"
  fullconversation: true  # Send full conversation history with each request
```

#### Politeness Validation

By default, ReplicantX focuses on functional API validation. However, you can optionally enable politeness/conversational tone validation:

```yaml
# Disable politeness validation (default) - focuses on functional responses
validate_politeness: false

# Enable politeness validation - also checks for conversational tone
validate_politeness: true
```

**When to use politeness validation:**
- ✅ **Customer-facing APIs** where tone matters
- ✅ **Chatbots and conversational AI** services
- ✅ **User experience testing** scenarios

**When to skip politeness validation:**
- ❌ **Internal APIs** focused on functionality
- ❌ **Data APIs** returning structured responses
- ❌ **Technical integrations** where tone is irrelevant

**Note:** Politeness validation is subjective and based on common conversational patterns. It looks for polite phrases like "please", "thank you", "how can I help", question patterns, and helpful language.

### CLI Commands

```bash
# Run all tests in a directory
replicantx run tests/*.yaml --report report.md

# Run with CI mode (exits 1 on failure)
replicantx run tests/*.yaml --report report.md --ci

# Run specific test file
replicantx run tests/specific_test.yaml

# Real-time conversation monitoring
replicantx run tests/*.yaml --watch

# Technical debugging with detailed logs
replicantx run tests/*.yaml --debug

# Combined monitoring and debugging
replicantx run tests/*.yaml --debug --watch

# Run tests in parallel for faster execution
replicantx run tests/*.yaml --parallel

# Run with limited concurrency to prevent API overload
replicantx run tests/*.yaml --parallel --max-concurrent 3

# Write browser issue bundles locally without filing GitHub issues
replicantx run tests/browser_test.yaml --issue-mode draft-only --issue-artifact-upload off

# Auto-file high-confidence browser issues to a GitHub repo
replicantx run tests/browser_test.yaml --issue-mode auto-high-confidence --issue-repo HelixTechnologies/helix-agent

# Override or supply a repo-specific Logfire query definition
replicantx run tests/browser_test.yaml --issue-mode draft-only --logfire-config replicantx.logfire.yaml

# Validate test files without running
replicantx validate tests/*.yaml --verbose
```

### 📊 Real-time Monitoring & Debugging

ReplicantX provides comprehensive monitoring and debugging capabilities to help you understand what's happening during test execution.

#### 🔍 **Watch Mode (`--watch`)**

Real-time conversation monitoring for observing test execution as it happens:

```bash
replicantx run tests/agent_test.yaml --watch
```

**What you see:**
- 👥 **Live conversation setup** with goal and facts
- 👤 **Replicant messages** as they're sent (with timestamps)
- ⏱️ **Response waiting indicators**
- 🤖 **Agent responses** as received
- ✅/❌ **Step results** with pass/fail status and timing
- 📊 **Final summary** with success rate, duration, goal achievement

**Perfect for:**
- ✅ **Live demos** - Show clients real AI conversations
- ✅ **Test monitoring** - Watch long-running tests progress
- ✅ **User experience validation** - See conversation flow
- ✅ **Performance monitoring** - Track response times

**Example Output:**
```
[22:04:42] 👥 LIVE CONVERSATION - Starting agent scenario
[22:04:42] 🎯 Goal: Book a business class flight to Paris
[22:04:42] 👤 Replicant: Hi, I'd like to book a flight to Paris.
[22:04:52] ✅ Step 1: PASSED (10.2s)
[22:04:52] 🤖 Agent: What cabin class would you prefer?
[22:04:53] 👤 Replicant: Business class, please.
[22:05:03] ✅ Step 2: PASSED (9.8s)
```

#### 🔧 **Debug Mode (`--debug`)**

Technical deep-dive with detailed system information:

```bash
replicantx run tests/agent_test.yaml --debug
```

**What you see:**
- 🔍 **HTTP client setup** (URL, timeout, auth provider, headers)
- 🔍 **Replicant agent initialization** (goal, facts, AI model settings)
- 🔍 **HTTP requests** (payload details, conversation history)
- 🔍 **API responses** (status codes, latency, content preview)
- 🔍 **Response validation** (assertion counts, individual results)
- 🔍 **AI processing** (response parsing, message generation)

**Perfect for:**
- 🔍 **Troubleshooting** - Diagnose failed assertions
- 🔍 **Performance tuning** - Analyze HTTP latency and bottlenecks
- 🔍 **Integration debugging** - Check payload formats and API calls
- 🔍 **AI behavior analysis** - Understand PydanticAI decision making

**Example Output:**
```
🔍 DEBUG HTTP Client initialized
   ├─ base_url: https://api.example.com/chat
   ├─ timeout: 120s
   ├─ auth_provider: supabase
   ├─ auth_headers: 2 headers

🔍 DEBUG HTTP request payload
   ├─ message: Hi, I'd like to book a flight to Paris.
   ├─ conversation_history_length: 1
   ├─ payload_size: 229 chars

🔍 DEBUG Response validation completed
   ├─ total_assertions: 2
   ├─ passed_assertions: 2
   ├─ overall_passed: True
```

#### 🎯 **Combined Mode (`--debug --watch`)**

Get both real-time conversation flow and technical details:

```bash
replicantx run tests/agent_test.yaml --debug --watch
```

**Perfect for:**
- 🎯 **Development** - Full visibility during feature building
- 🎯 **Complex debugging** - When you need everything
- 🎯 **Training** - Teaching others how the system works
- 🎯 **Comprehensive analysis** - Complete test execution insight

#### 💡 **Monitoring Tips**

**For Long-running Tests:**
```bash
# Watch progress while generating a report
replicantx run tests/*.yaml --watch --report detailed.md
```

**For CI/CD Debugging:**
```bash
# Debug mode with CI exit codes
replicantx run tests/*.yaml --debug --ci
```

**For Performance Analysis:**
```bash
# Combined with verbose output
replicantx run tests/*.yaml --debug --verbose --report performance.json
```

### ⚡ Parallel Test Execution

ReplicantX supports parallel execution of test scenarios for significantly faster test runs, especially when testing multiple scenarios against the same API.

#### 🚀 **Basic Parallel Execution**

Run all scenarios in parallel (overrides individual scenario settings):

```bash
# Run all tests in parallel
replicantx run tests/*.yaml --parallel

# Run with limited concurrency to prevent API overload
replicantx run tests/*.yaml --parallel --max-concurrent 3
```

#### 📋 **Per-Scenario Configuration**

Control parallel execution at the scenario level:

```yaml
# tests/parallel_scenario.yaml
name: "Parallel Test Scenario"
base_url: "https://api.example.com/chat"
auth:
  provider: noop
level: basic
parallel: true  # Enable parallel execution for this scenario
steps:
  - user: "Hello, test message"
    expect_contains: ["response"]
```

```yaml
# tests/sequential_scenario.yaml
name: "Sequential Test Scenario"
base_url: "https://api.example.com/chat"
auth:
  provider: noop
level: basic
parallel: false  # Run sequentially (default)
steps:
  - user: "Hello, test message"
    expect_contains: ["response"]
```

#### 🔄 **Execution Modes**

**Automatic Detection:**
- If any scenario has `parallel: true`, all scenarios run in parallel
- If `--parallel` flag is used, all scenarios run in parallel (overrides individual settings)
- Otherwise, scenarios run sequentially

**Mixed Execution:**
```bash
# Some scenarios parallel, some sequential - all run in parallel
replicantx run tests/parallel_*.yaml tests/sequential_*.yaml
```

#### ⚙️ **Concurrency Control**

**Unlimited Concurrency (Default):**
```bash
replicantx run tests/*.yaml --parallel
```

**Limited Concurrency:**
```bash
# Limit to 3 concurrent scenarios
replicantx run tests/*.yaml --parallel --max-concurrent 3

# Limit to 1 (effectively sequential but with parallel infrastructure)
replicantx run tests/*.yaml --parallel --max-concurrent 1
```

#### 📊 **Performance Benefits**

**Example: 10 scenarios, each taking 5 seconds**

| Mode | Duration | Speed Improvement |
|------|----------|-------------------|
| Sequential | ~50 seconds | 1x |
| Parallel (unlimited) | ~5 seconds | 10x |
| Parallel (max 3) | ~17 seconds | 3x |

#### ⚠️ **Considerations**

**API Rate Limits:**
- Use `--max-concurrent` to avoid overwhelming your API
- Monitor API response times during parallel execution
- Consider your API's rate limiting policies

**Resource Usage:**
- Parallel execution uses more memory and network connections
- Monitor system resources during large parallel test runs

**Test Dependencies:**
- Tests that depend on execution order should use `parallel: false`
- Consider using sequential execution for tests that modify shared state

**Debugging:**
- Parallel execution may make debugging more complex
- Use `--verbose` to see detailed output from all scenarios
- Consider running problematic tests sequentially for debugging

### Authentication Providers

#### Supabase
```yaml
auth:
  provider: supabase
  email: user@example.com
  password: password123
  project_url: "{{ env.SUPABASE_URL }}"
  api_key: "{{ env.SUPABASE_ANON_KEY }}"
```

#### Supabase Magic Link (Browser Mode)
```yaml
auth:
  provider: supabase_magic_link
  project_url: "{{ env.SUPABASE_URL }}"
  service_role_key: "{{ env.SUPABASE_SERVICE_ROLE_KEY }}"
  user_mode: generated  # Auto-generates unique email
  # Or use fixed user:
  # user_mode: fixed
  # email: "test@example.com"
  app_refresh_endpoint: "https://app.example.com/auth/refresh"
```

#### JWT
```yaml
auth:
  provider: jwt
  token: "{{ env.JWT_TOKEN }}"
```

#### No Authentication
```yaml
auth:
  provider: noop
```

## 🤖 Replicant Agent System

The Replicant agent is a Pydantic-based intelligent conversational agent that:

### Key Features
- **Fact-Based Responses**: Uses configured facts to answer API questions intelligently
- **Natural Conversation**: Acts like a real user who doesn't provide all information upfront
- **Customizable Behavior**: System prompts allow different personalities and response patterns
- **Goal-Oriented**: Works toward specific objectives with completion detection
- **Context Awareness**: Maintains conversation history and state

### LLM-Powered Fact Usage
The agent intelligently uses configured facts through LLM integration:
- **Context-aware**: LLMs understand when facts are relevant to questions
- **Natural integration**: Facts are woven naturally into conversation responses  
- **Smart timing**: Agent knows when to volunteer information vs. wait to be asked
- **Conversation memory**: Recent chat history provides context for fact usage

### Conversation State Management
ReplicantX provides flexible conversation state management to handle different API architectures:

#### Full Conversation History (`fullconversation: true`)
Sends the complete conversation history (including all responses) with each request:
```yaml
replicant:
  fullconversation: true  # Default behavior
```

**Benefits:**
- ✅ **Complete Context**: API receives full conversation state
- ✅ **Stateless APIs**: Works with APIs that don't maintain session state
- ✅ **Microservices**: Suitable for distributed systems
- ✅ **Testing Realism**: Mimics real-world stateless interactions

#### Limited History (`fullconversation: false`)
Sends only the last 10 messages for performance:
```yaml
replicant:
  fullconversation: false
```

**Use Cases:**
- 🔧 **Performance Testing**: Reduce payload size for high-volume testing
- 🔧 **Legacy APIs**: Compatible with APIs expecting limited context
- 🔧 **Memory Constraints**: When API has payload size limitations

### API Payload Format Configuration
ReplicantX supports multiple API payload formats for maximum compatibility with any conversational API:

#### OpenAI Format (`payload_format: openai`) - **Default**
Industry-standard OpenAI chat completion format:
```yaml
replicant:
  payload_format: openai  # Default behavior
```

**Payload Structure:**
```json
{
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
    {"role": "user", "content": "How are you?"}
  ]
}
```

**Best For:**
- ✅ **OpenAI APIs** and compatible services
- ✅ **Industry standard** - widely supported
- ✅ **Full conversation context** with message arrays
- ✅ **Modern conversational AI** platforms

#### Simple Format (`payload_format: simple`)
Minimal message-only format for basic APIs:
```yaml
replicant:
  payload_format: simple
```

**Payload Structure:**
```json
{
  "message": "Hello, how are you?"
}
```

**Best For:**
- ✅ **Simple APIs** that only need the current message
- ✅ **Performance-critical** scenarios
- ✅ **Legacy systems** with minimal payload requirements
- ✅ **Testing basic functionality** without conversation context

#### Anthropic Format (`payload_format: anthropic`)
Anthropic Claude-compatible format:
```yaml
replicant:
  payload_format: anthropic
```

**Payload Structure:**
```json
{
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

**Best For:**
- ✅ **Anthropic Claude APIs** and compatible services
- ✅ **Claude-based applications** and integrations
- ✅ **Conversational AI** platforms using Claude models

#### Legacy Format (`payload_format: legacy`)
Original ReplicantX format for backward compatibility:
```yaml
replicant:
  payload_format: legacy
```

**Payload Structure:**
```json
{
  "message": "Hello, how are you?",
  "timestamp": "2025-07-09T10:30:00",
  "conversation_history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

**Best For:**
- 🔧 **Existing ReplicantX integrations** (backward compatibility)
- 🔧 **Custom APIs** expecting the original format
- 🔧 **Migration scenarios** when transitioning to new formats

#### Session Management

ReplicantX supports session management to maintain conversation state across multiple API requests without sending the full conversation history each time. This is more efficient and realistic for production APIs.

##### Session Modes

```yaml
replicant:
  # Session management configuration
  session_mode: auto  # disabled, auto, fixed, or env
  session_id: null  # Required when session_mode is "fixed"
  session_timeout: 300  # Session timeout in seconds (default: 5 minutes)
  session_format: uuid  # replicantx or uuid (default: uuid)
  session_placement: body  # header, body, or url (default: body)
  session_variable_name: session_id  # Custom name for session variable
```

**Session Modes:**
- `disabled` (default): No session management, uses full conversation history
- `auto`: Auto-generate unique session ID for each test run
- `fixed`: Use a specific session ID (requires `session_id` field)
- `env`: Use session ID from `REPLICANTX_SESSION_ID` environment variable

**Session Formats:**
- `uuid` (default): Standard UUID format (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- `replicantx`: ReplicantX format (e.g., `replicantx_c8ff856c`)

**Session Placement:**
- `body` (default): Session ID in request body/payload
- `header`: Session ID in HTTP headers
- `url`: Session ID in URL path (RESTful)

**Session Variable Name:**
- Custom name for the session variable in headers or body
- Examples: `session_id`, `conversation_id`, `x-conversation-id`, `chat_id`

**Session-Aware Payload Formats:**
- `openai_session`: OpenAI-compatible with session support
- `simple_session`: Simple format with session support
- `restful_session`: RESTful format with session support

##### Example Configurations

**Auto-Generated UUID Session (Recommended):**
```yaml
replicant:
  session_mode: auto
  session_format: uuid  # Standard UUID format
  session_placement: body
  session_variable_name: session_id
  payload_format: openai_session
  fullconversation: false
  session_timeout: 600  # 10 minutes
```

**ReplicantX Format with Header:**
```yaml
replicant:
  session_mode: auto
  session_format: replicantx  # ReplicantX format
  session_placement: header
  session_variable_name: x-conversation-id
  payload_format: openai_session
  fullconversation: false
```

**Fixed Session ID with Custom Variable:**
```yaml
replicant:
  session_mode: fixed
  session_id: "test_session_12345"
  session_format: uuid
  session_placement: body
  session_variable_name: conversation_id
  payload_format: simple_session
  fullconversation: false
```

**RESTful Session (Session ID in URL):**
```yaml
replicant:
  session_mode: auto
  session_format: uuid
  session_placement: url
  payload_format: restful_session
  fullconversation: false
# Results in requests to: /conversations/{session_id}/messages
```

**Environment-Based Session with Header:**
```bash
# Set environment variable
export REPLICANTX_SESSION_ID="prod_session_abc123"

# Use in YAML
replicant:
  session_mode: env
  session_format: uuid
  session_placement: header
  session_variable_name: x-chat-id
  payload_format: openai_session
  fullconversation: false
```

##### Session Management Benefits

**✅ Efficiency:**
- Reduces payload size significantly
- Faster API requests
- Lower bandwidth usage

**✅ Realistic Testing:**
- Matches production API patterns
- Tests session handling logic
- Validates conversation continuity

**✅ Flexibility:**
- Multiple session ID strategies
- Configurable timeouts
- Different payload formats

**✅ Debugging:**
- Session information in debug logs
- Session lifecycle tracking
- Timeout monitoring

##### When to Use Session Management

**Use session management when:**
- ✅ Your API supports conversation IDs
- ✅ You want to test session handling
- ✅ Payload size is a concern
- ✅ Testing production-like scenarios

**Use full conversation when:**
- ❌ API doesn't support sessions
- ❌ Testing legacy endpoints
- ❌ Need complete conversation context
- ❌ Debugging conversation flow

### Complete Configuration Example
```yaml
name: "Universal API Test"
base_url: https://api.example.com/chat
auth:
  provider: noop
level: agent
replicant:
  goal: "Test API with OpenAI-compatible format"
  facts:
    name: "Test User"
    email: "test@example.com"
  system_prompt: |
    You are a helpful user testing an API.
  initial_message: "Hello, I'm testing the API."
  max_turns: 10
  completion_keywords: ["complete", "finished", "done"]
  fullconversation: true  # Send full conversation history
  payload_format: openai  # Use OpenAI-compatible format
  llm:
    model: "test"
    temperature: 0.7
    max_tokens: 150
```

### Session Management Examples

**UUID Format with Header (Recommended for APIs):**
```yaml
name: "Flight Booking with UUID Header"
base_url: "https://api.example.com/chat"
auth:
  provider: "noop"
level: "agent"
replicant:
  goal: "Book a flight from London to Paris"
  facts:
    name: "Alex Johnson"
    email: "alex@example.com"
    departure: "London"
    destination: "Paris"
    date: "next Friday"
  system_prompt: "You are a customer booking a flight. Be polite and provide details when asked."
  initial_message: "Hi, I need to book a flight from London to Paris for next Friday."
  max_turns: 15
  session_mode: auto
  session_format: uuid  # Standard UUID format
  session_placement: header  # In HTTP headers
  session_variable_name: x-conversation-id  # Custom header name
  payload_format: openai_session
  fullconversation: false
  session_timeout: 600
  llm:
    model: "test"
```

**ReplicantX Format with Body:**
```yaml
name: "Customer Support with ReplicantX Body"
base_url: "https://api.example.com/support"
auth:
  provider: "noop"
level: "agent"
replicant:
  goal: "Get help with billing issue"
  facts:
    name: "Sarah Chen"
    account_id: "ACC-789456"
    issue: "billing"
  system_prompt: "You are a customer with a billing question."
  initial_message: "Hello, I have a billing question."
  max_turns: 10
  session_mode: auto
  session_format: replicantx  # ReplicantX format
  session_placement: body  # In request body
  session_variable_name: conversation_id  # Custom variable name
  payload_format: simple_session
  fullconversation: false
  session_timeout: 300
  llm:
    model: "test"
```

**UUID Format with URL (RESTful):**
```yaml
name: "Pizza Order with UUID URL"
base_url: "https://api.example.com"
auth:
  provider: "noop"
level: "agent"
replicant:
  goal: "Order a pizza for delivery"
  facts:
    name: "Mike Rodriguez"
    address: "123 Main St, NYC"
    phone: "+1 555 123 4567"
  system_prompt: "You are ordering a pizza. Be friendly and provide your details."
  initial_message: "Hi, I'd like to order a pizza for delivery."
  max_turns: 8
  session_mode: auto
  session_format: uuid  # UUID format
  session_placement: url  # In URL path
  payload_format: restful_session
  fullconversation: false
  # Results in requests to: /conversations/{uuid}/messages
  llm:
    model: "test"
```

### Migration Guide

**From Legacy to OpenAI Format:**
```yaml
# Old configuration (still works)
replicant:
  payload_format: legacy  # or omit entirely

# New recommended configuration
replicant:
  payload_format: openai  # More compatible with modern APIs
```

**For Simple APIs:**
```yaml
replicant:
  payload_format: simple
  fullconversation: false  # Not needed for simple format
```

**For Anthropic APIs:**
```yaml
replicant:
  payload_format: anthropic
  fullconversation: true  # Maintain conversation context
```

### System Prompt Examples

**Helpful User:**
```yaml
system_prompt: |
  You are a polite user trying to achieve your goal. You have the 
  necessary information but need prompting to remember details.
```

**Forgetful Customer:**
```yaml
system_prompt: |
  You are a customer who sometimes forgets details and needs 
  multiple prompts. You're friendly but can be a bit scattered.
```

**Demanding User:**
```yaml
system_prompt: |
  You are an impatient user who wants quick results. You provide 
  information when asked but expect efficient service.
```

## 🎯 Goal Evaluation Modes

ReplicantX provides intelligent goal evaluation to accurately determine when conversation objectives have been achieved, solving the common problem of false positives with simple keyword matching.

### The Problem with Keywords

Traditional keyword-based completion detection can produce false positives:

```yaml
# Problematic scenario
completion_keywords: ["confirmed", "booked"]

# False positive examples:
# ❌ "I'll let you know when your booking has been confirmed" (contains "confirmed")
# ❌ "Have you booked with us before?" (contains "booked") 
# ❌ "Your booking confirmation is pending" (contains "booking")
```

### Three Evaluation Modes

#### 1. **Keywords Mode** (Default - Backwards Compatible)
Simple substring matching - the original behavior:

```yaml
replicant:
  goal: "Book a flight to Paris"
  goal_evaluation_mode: "keywords"  # Default
  completion_keywords: ["confirmed", "booked", "reservation number"]
```

**Use when:**
- ✅ Maintaining existing test compatibility
- ✅ Simple scenarios with clear completion signals
- ✅ Performance is critical (no LLM calls)

**Reporting:** Simplified reporting that focuses on keyword matching:
- Watch mode shows: `🔍 Keyword matched: (matched: confirmed, booked)` or `🔍 No completion keywords found`
- Justification shows: `Goal achieved via keyword matching: Keyword evaluation: Found completion keywords (matched: confirmed, booked)`
- JSON reports include simple `keyword_result` field instead of detailed reasoning

#### 2. **Intelligent Mode** (Recommended)
LLM-powered analysis that understands context and intent:

```yaml
replicant:
  goal: "Book a business class flight to Paris"
  goal_evaluation_mode: "intelligent"
  goal_evaluation_model: "openai:gpt-4o-mini"  # Optional: separate model for evaluation
  completion_keywords: ["confirmed", "booked"]  # Still required for compatibility
```

**Benefits:**
- ✅ **Context-aware**: Distinguishes promises from accomplishments
- ✅ **False positive reduction**: "I'll confirm later" ≠ "Your booking is confirmed"
- ✅ **Intent understanding**: Recognizes goal completion without exact keywords
- ✅ **Reasoning provided**: Detailed explanation of evaluation decisions

**Reporting:** Detailed reporting with full analysis:
- Watch mode shows: `🧠 Evaluation method: intelligent`, `📊 Confidence: 0.85`, `💭 Reasoning: Detailed explanation...`
- Justification includes confidence scores and detailed reasoning
- JSON reports include full evaluation metadata (confidence, reasoning, fallback_used)

#### 3. **Hybrid Mode** (Best of Both Worlds)
Attempts LLM evaluation first, falls back to keywords if uncertain:

```yaml
replicant:
  goal: "Get help with billing issue"
  goal_evaluation_mode: "hybrid"
  goal_evaluation_model: "openai:gpt-4o-mini"
  completion_keywords: ["resolved", "ticket created", "issue closed"]
```

**Benefits:**
- ✅ **Smart evaluation** when LLM is confident
- ✅ **Reliable fallback** when LLM is uncertain
- ✅ **Cost-effective** for mixed scenarios
- ✅ **Production-ready** with built-in safety net

### Custom Evaluation Prompts

For domain-specific scenarios, customize the evaluation logic:

```yaml
replicant:
  goal: "Complete a customer support ticket"
  goal_evaluation_mode: "intelligent"
  goal_evaluation_prompt: |
    Evaluate if the customer support goal is achieved. Look for:
    1. Issue resolution confirmation from the agent
    2. Ticket number or reference provided
    3. Customer satisfaction or acknowledgment
    4. Clear closure statements
    
    Goal: {goal}
    User Facts: {facts}
    Recent Conversation: {conversation}
    
    Respond exactly:
    RESULT: [ACHIEVED or NOT_ACHIEVED]
    CONFIDENCE: [0.0 to 1.0]
    REASONING: [Brief explanation]
  completion_keywords: ["resolved", "ticket created"]
```

### Example: Flight Booking with Intelligent Evaluation

```yaml
name: "Smart Flight Booking Test"
base_url: "https://api.example.com/chat"
auth:
  provider: noop
level: agent
replicant:
  goal: "Book a round-trip business class flight to Paris"
  facts:
    name: "Sarah Johnson"
    email: "sarah@example.com"
    travel_class: "business"
    destination: "Paris"
    departure_city: "New York"
    travel_date: "next Friday"
    return_date: "following Monday"
    budget: "$3000"
  system_prompt: |
    You are a customer booking a flight. Provide information when asked
    but don't volunteer everything upfront. Be conversational and natural.
  initial_message: "Hi, I'd like to book a flight to Paris."
  max_turns: 15
  
  # Intelligent goal evaluation
  goal_evaluation_mode: "intelligent"
  goal_evaluation_model: "openai:gpt-4o-mini"  # Fast, cost-effective model
  
  # Still needed for fallback/compatibility  
  completion_keywords: ["booked", "confirmed", "reservation number"]
  
  llm:
    model: "openai:gpt-4o"
    temperature: 0.7
    max_tokens: 150
```

### Evaluation Results in Reports

The watch mode now shows detailed evaluation information:

```bash
📊 CONVERSATION COMPLETE
🏁 Status: ✅ SUCCESS
🎯 Goal achieved: Yes
🧠 Evaluation method: intelligent
📊 Confidence: 0.89
💭 Reasoning: The flight has been successfully booked with confirmation number ABC123 provided
```

### Migration Strategy

**Phase 1: Test Intelligent Mode**
```yaml
# Update specific tests to use intelligent evaluation
goal_evaluation_mode: "intelligent"
```

**Phase 2: Adopt Hybrid Mode**
```yaml
# Use hybrid for safety while gaining intelligence
goal_evaluation_mode: "hybrid"
```

**Phase 3: Gradual Rollout**
```yaml
# Eventually make intelligent/hybrid the default for new tests
goal_evaluation_mode: "intelligent"
```

### When to Use Each Mode

| Mode | Use Case | Pros | Cons |
|------|----------|------|------|
| **keywords** | Legacy tests, simple APIs | Fast, deterministic | False positives |
| **intelligent** | Modern apps, complex goals | Accurate, context-aware | Requires LLM |
| **hybrid** | Production, mixed scenarios | Smart + safe fallback | Slightly more complex |

**Recommendation**: Start with `hybrid` mode for new tests to get the benefits of intelligent evaluation with keyword fallback safety.

### 🧪 Try the Example

See a complete example that demonstrates false positive prevention:

```bash
# Download the example test
curl -O https://raw.githubusercontent.com/helixtechnologies/replicantx/main/tests/intelligent_evaluation_example.yaml

# Run with intelligent evaluation
replicantx run intelligent_evaluation_example.yaml --watch

# Compare with keyword-only mode by changing goal_evaluation_mode to "keywords"
```

This example shows how intelligent evaluation distinguishes between:
- ❌ "I'll create a ticket for your issue" (promise)
- ✅ "Your refund has been processed, reference #REF123" (completion)

## 🧠 LLM Integration

ReplicantX uses **PydanticAI** for powerful LLM integration with multiple providers:

### Supported Providers

- **OpenAI**: GPT-4, GPT-4o, and other OpenAI models
- **Anthropic**: Claude 4.0 Sonnet, Claude 4 Haiku, and other Claude models
- **Google**: Gemini models via Google AI and VertexAI
- **Groq**: Fast inference with Llama, Mixtral, and other models
- **Ollama**: Local LLM deployment
- **Test**: Built-in test model for development (no API keys needed)

### Configuration

Add LLM configuration to your agent scenarios using PydanticAI model strings:

*Technical Support Example:*
```yaml
level: agent
replicant:
  goal: "Get technical support for my account"
  facts:
    name: "Jordan Smith"
    # ... other facts
  system_prompt: |
    You are a customer seeking help with a technical issue.
    Use your available facts to answer questions naturally.
  # ... other config
  llm:
    model: "openai:gpt-4.1-mini"     # PydanticAI model string
    temperature: 0.7           # Response creativity (0.0-1.0)
    max_tokens: 150            # Maximum response length
```

*Flight Booking Example:*
```yaml
level: agent
replicant:
  goal: "Book a business class flight to Paris"
  facts:
    name: "Sarah Johnson"
    destination: "Paris"
    travel_class: "business"
    # ... other facts
  system_prompt: |
    You are a customer trying to book a flight. You have the 
    necessary information but don't provide all details upfront.
  # ... other config
  llm:
    model: "anthropic:claude-3-5-sonnet-latest"  # PydanticAI model string
    temperature: 0.8           # Response creativity (0.0-1.0)
    max_tokens: 200            # Maximum response length
```

### Model String Examples

```yaml
# OpenAI models
model: "openai:gpt-4o"
model: "openai:gpt-4.1-mini"
model: "openai:gpt-4.1-nano"

# Anthropic models  
model: "anthropic:claude-3-5-sonnet-latest"
model: "anthropic:claude-3-haiku-20240307"

# Google models
model: "gemini-1.5-pro"
model: "gemini-1.5-flash"

# Groq models
model: "groq:llama-3.1-8b-instant"
model: "groq:mixtral-8x7b-32768"

# Test model (no API key needed)
model: "test"
```

### Environment Variables

PydanticAI automatically detects API keys from environment variables:

```bash
# OpenAI
export OPENAI_API_KEY=sk-your-api-key

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-your-api-key

# Google AI
export GOOGLE_API_KEY=your-google-api-key

# Groq
export GROQ_API_KEY=your-groq-api-key
```

### Installation with LLM Support

```bash
# Install with all LLM providers
pip install replicantx[all]

# Install with specific providers
pip install replicantx[openai]
pip install replicantx[anthropic]

# Core installation (includes PydanticAI with test model)
pip install replicantx
```

### How LLM Integration Works

1. **Smart Prompting**: System prompts are enhanced with available facts and conversation context
2. **Natural Responses**: LLMs generate contextually appropriate responses based on user personas
3. **Fact Integration**: Available facts are automatically included in prompts for relevant responses
4. **Graceful Fallback**: If LLM calls fail, the system falls back to rule-based responses
5. **Conversation Memory**: Recent conversation history is maintained for context

### Examples with PydanticAI

*Customer Support Example:*
```yaml
name: "Customer Support - Billing Issue"
base_url: https://api.example.com/support
auth:
  provider: noop
level: agent
replicant:
  goal: "Get customer support for billing issue"
  facts:
    name: "Alex Chen"
    account_number: "ACC-12345"
    issue_type: "billing"
    last_payment: "$99.99 on Jan 15th"
  system_prompt: |
    You are a customer who is polite but slightly frustrated about 
    a billing issue. You have the necessary account information but 
    may need prompting to remember specific details.
  initial_message: "Hi, I have a question about my recent bill."
  max_turns: 12
  completion_keywords: ["resolved", "ticket created", "issue closed"]
  fullconversation: true  # Send full conversation history with each request
  payload_format: openai  # Use OpenAI-compatible format
  llm:
    model: "openai:gpt-4o"  # PydanticAI model string
    temperature: 0.8
    max_tokens: 120
```

*Flight Booking Example:*
```yaml
name: "Travel Booking - Flight to Paris"
base_url: https://api.example.com/chat
auth:
  provider: supabase
  project_url: "{{ env.SUPABASE_URL }}"
  api_key: "{{ env.SUPABASE_ANON_KEY }}"
  email: "{{ env.TEST_USER_EMAIL }}"
  password: "{{ env.TEST_USER_PASSWORD }}"
level: agent
replicant:
  goal: "Book a business class flight to Paris for next weekend"
  facts:
    name: "Sarah Johnson"
    email: "sarah.johnson@example.com"
    travel_class: "business"
    destination: "Paris"
    departure_city: "New York"
    travel_date: "next Friday"
    passengers: 1
    budget: "$3000"
    preferences: "aisle seat, vegetarian meal"
  system_prompt: |
    You are a helpful user trying to book a flight. You have all the 
    necessary information but you're a typical user who doesn't 
    provide all details upfront.
  initial_message: "Hi, I'd like to book a flight to Paris for next weekend."
  max_turns: 15
  completion_keywords: ["booked", "confirmed", "reservation number", "booking complete"]
  fullconversation: true  # Send full conversation history with each request
  payload_format: openai  # Use OpenAI-compatible format
  llm:
    model: "openai:gpt-4o"
    temperature: 0.7
    max_tokens: 150
```


These examples enable much more natural and contextually aware conversations compared to rule-based responses.

## 🔧 GitHub Actions Integration

Add this workflow to `.github/workflows/replicantx.yml`:

```yaml
name: ReplicantX E2E Tests
on:
  pull_request: { types: [opened, synchronize, reopened] }
jobs:
  replicantx:
    runs-on: ubuntu-latest
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
      REPLICANTX_TARGET: pr-${{ github.event.pull_request.number }}-helix-api.onrender.com
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install "replicantx[cli]"
      - run: |
          until curl -sf "https://$REPLICANTX_TARGET/health"; do
            echo "Waiting for preview…"; sleep 5; done
      - run: replicantx run tests/*.yaml --report report.md --ci
      - uses: marocchino/sticky-pull-request-comment@v2
        if: always()
        with: { path: report.md }
```
