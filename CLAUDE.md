# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ReplicantX** is an end-to-end testing harness for AI agents that communicate via HTTP APIs or web browsers. It enables comprehensive testing of conversational AI systems with support for intelligent agents, multiple authentication methods, browser automation, and detailed reporting.

**Stack**: Python 3.11+, Pydantic v2, PydanticAI, httpx, Typer, Rich, Playwright
**Structure**: Modular architecture with pluggable auth, payload formatters, and reporters

📖 **For detailed architecture and module documentation, see [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md)**
🌐 **For browser mode configuration guide, see [docs/browser-mode-config.md](docs/browser-mode-config.md)**

## Development Commands

### Installation
```bash
# Basic installation
pip install -e .

# With CLI extras
pip install -e ".[cli]"

# With all LLM providers
pip install -e ".[all]"

# Development dependencies
pip install -e ".[dev]"

# Install Playwright browsers (for browser mode)
playwright install
```

### Code Quality
```bash
# Format code with black (line length: 88)
black replicantx/

# Sort imports with isort (black profile)
isort replicantx/

# Type checking with mypy (strict mode)
mypy replicantx/

# Run all quality checks together
black replicantx/ && isort replicantx/ && mypy replicantx/
```

### Testing
```bash
# Run pytest tests
pytest

# Run specific test file
pytest tests/test_specific.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=replicantx
```

### CLI Testing
```bash
# Validate test scenario files
replicantx validate tests/*.yaml

# Run test scenarios
replicantx run tests/*.yaml

# Run with report generation
replicantx run tests/*.yaml --report report.md

# Run with CI mode (exits with non-zero on failure)
replicantx run tests/*.yaml --ci

# Run with debug output
replicantx run tests/*.yaml --debug

# Run with watch mode (real-time monitoring)
replicantx run tests/*.yaml --watch

# Run tests in parallel
replicantx run tests/*.yaml --parallel --max-concurrent 3

# Browser mode: watch the actual browser window
# set replicant.browser.headless: false in the YAML, then run:
replicantx run tests/browser_test.yaml --watch

# Browser mode: write local issue drafts only
replicantx run tests/browser_test.yaml --issue-mode draft-only --issue-artifact-upload off

# Browser mode: auto-file high-confidence issues
replicantx run tests/browser_test.yaml --issue-mode auto-high-confidence --issue-repo HelixTechnologies/helix-agent

# Browser mode: View traces (after test completes)
playwright show-trace artifacts/trace.zip
```

## Architecture

### Core Components

**Package Structure:**
```
replicantx/
├── cli.py              # Typer-based CLI entry point
├── models.py           # Pydantic models for configuration and results
├── scenarios/          # Test scenario runners
│   ├── basic.py        # Fixed message scenarios (Level 1)
│   ├── agent.py        # Intelligent agent scenarios (Level 2 - API mode)
│   ├── browser_agent.py # Browser automation scenarios (Level 2 - Browser mode)
│   └── replicant.py    # Core Replicant agent implementation
├── auth/               # Authentication providers
│   ├── base.py         # Base authentication class
│   ├── supabase.py     # Supabase auth implementation
│   ├── jwt.py          # JWT token auth
│   ├── noop.py         # No authentication
│   └── magic_link.py   # Supabase magic link auth (for browser mode)
├── reporters/          # Output formatters
│   ├── markdown.py     # Markdown report generation
│   └── json.py         # JSON report generation
└── tools/              # Utility modules
    ├── http_client.py  # HTTP client with retry logic
    ├── payload_formatter.py  # API payload format support
    ├── session_manager.py    # Session management
    └── browser/        # Browser automation toolkit
        ├── observation.py        # Page observation extraction
        ├── actions.py            # Browser action execution
        ├── artifacts.py           # Trace & screenshot management
        └── playwright_manager.py  # Playwright driver
```

### Test Levels

**Level 1 (Basic):** Fixed user messages with deterministic assertions
- Defined in `scenarios/basic.py`
- Simple step-by-step conversations
- Assertions: `expect_contains`, `expect_regex`, `expect_equals`, `expect_not_contains`

**Level 2 (Agent):** Intelligent AI-powered Replicant agents
- **API Mode**: `scenarios/agent.py` - HTTP API testing with structured messages
- **Browser Mode**: `scenarios/browser_agent.py` - Playwright browser automation with visual interaction
- Uses PydanticAI for LLM integration
- Configurable facts, goals, and personalities
- Goal evaluation with intelligent analysis

### Authentication System

Pluggable authentication providers in `auth/`:
- **noop**: No authentication (default)
- **supabase**: Supabase email/password authentication
- **supabase_magic_link**: Supabase magic link with admin API (for browser mode, supports auto-generated users)
- **jwt**: JWT token-based authentication

All providers inherit from `auth/base.py` base class.

### Payload Formats

Multiple API payload formats for compatibility:
- **openai**: OpenAI chat completion format (default)
- **simple**: Minimal message-only format
- **anthropic**: Anthropic Claude-compatible format
- **legacy**: Original ReplicantX format (backward compatibility)

Session-aware variants: `openai_session`, `simple_session`, `restful_session`

### Replicant Agent System

The Replicant agent (`scenarios/replicant.py`) is a Pydantic-based intelligent conversational agent:
- **Fact-Based**: Uses configured facts intelligently through LLM
- **Context-Aware**: Maintains conversation history and state
- **Goal-Oriented**: Works toward specific objectives with completion detection
- **Customizable**: System prompts allow different personalities

**LLM Integration:**
- Uses PydanticAI for multi-provider support
- Supports OpenAI, Anthropic, Google, Groq, and local models
- Automatic API key detection from environment variables
- Built-in test model for development (no API key needed)

### Session Management

Flexible conversation state management in `tools/session_manager.py`:
- **Modes**: `disabled`, `auto`, `fixed`, `env`
- **Formats**: `uuid`, `replicantx`
- **Placement**: `header`, `body`, `url`
- Reduces payload size and tests production-like scenarios

### Goal Evaluation

Three evaluation modes for detecting conversation completion:
- **keywords**: Simple substring matching (default, backward compatible)
- **intelligent**: LLM-powered analysis with context awareness
- **hybrid**: Smart evaluation with keyword fallback

### Browser Mode (Playwright Automation)

**NEW**: Browser mode enables end-to-end testing of web applications using Playwright:
- **Interaction**: Chat-based interaction with automatic button/element detection
- **Visual Evaluation**: Screenshot-based goal evaluation using vision models
- **Smart Detection**: Heuristics for finding chat inputs and prioritizing elements
- **Magic Link Auth**: Supabase admin API for automated user generation

**Components in `tools/browser/`:**
- **observation.py**: Page observation with smart element ranking
- **actions.py**: Browser action execution (send_chat, click, fill, press, wait, scroll, navigate)
- **artifacts.py**: Trace and screenshot management
- **playwright_manager.py**: Playwright driver with lifecycle management

**Evidence Modes** (`browser.goal_evidence`):
- `dom`: Text/DOM-only evaluation (fastest)
- `screenshot`: Visual analysis with vision models (most accurate)
- `dom_then_screenshot`: Smart hybrid (recommended for production)
- `both`: Combined evaluation with confidence averaging

**Model Selection**:
- `llm.model`: Main model for response generation (e.g., `openai:gpt-4.1-mini`)
- `goal_evaluation_model`: Model for DOM-based evaluation
- `browser.screenshot_evaluation_model`: Vision model for screenshots (e.g., `openai:gpt-5.2`, `anthropic:claude-4-6-sonnet-latest`)

**Configuration**:
```yaml
replicant:
  interaction_mode: browser
  browser:
    start_url: "https://app.example.com"
    headless: true
    goal_evidence: dom_then_screenshot
    screenshot_evaluation_model: "openai:gpt-5.2"
```

**Standalone browser issue reporting:**
- Controlled from the CLI, not the scenario YAML
- `--issue-mode off|draft-only|auto-high-confidence`
- `--issue-repo owner/name`
- `--issue-artifact-upload on|off`
- `--issue-output <dir>`
- `--logfire-config <path>`
- Browser runs continue when non-blocking app errors occur and the Replicant can still make progress
- A scenario can pass and still emit an issue bundle or GitHub issue for a non-blocking bug
- Issue bundles are written as `issue_bundle.json` plus `issue.md` under the chosen issue output directory
- Logfire query config is auto-discovered from `replicantx.logfire.yaml` or `replicantx.logfire.yml`

### Environment Variables

ReplicantX automatically detects environment variables from `.env` files and system environment:

**LLM Integration:**
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GOOGLE_API_KEY`: Google AI API key
- `GROQ_API_KEY`: Groq API key

**Supabase Authentication:**
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_ANON_KEY`: Supabase anonymous key (for email/password auth)
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role key (for browser mode magic link auth)

**Target API:**
- `REPLICANTX_TARGET`: Target API domain
- `JWT_TOKEN`: JWT token for authentication

**Browser issue reporting:**
- `REPLICANTX_GITHUB_TOKEN`: GitHub token for standalone issue filing
- `REPLICANTX_LOGFIRE_API_KEY`: Logfire read token for server-side log enrichment
- `REPLICANTX_LOGFIRE_BASE_URL`: Optional Logfire API base URL override
- `REPLICANTX_LOGFIRE_SERVICE_NAME`: Optional Logfire service name override
- `REPLICANTX_LOGFIRE_CONFIG`: Optional path to a repo-specific Logfire query YAML file
- `REPLICANTX_ARTIFACT_BUCKET`: Optional Supabase Storage bucket name for uploaded artifacts
- `REPLICANTX_ARTIFACT_SIGNED_URL_TTL_SECONDS`: Optional signed URL TTL for uploaded artifacts
- `REPLICANTX_ENVIRONMENT`: Optional environment label included in bundles and issue bodies

**Custom Variables:**
- Reference in YAML with `{{ env.VARIABLE_NAME }}` syntax

### Reporting

Rich reporting in multiple formats:
- **Markdown**: Human-readable reports with timing and assertions
- **JSON**: Machine-readable reports for CI/CD integration
- Includes conversation transcripts, timing data, and assertion results

## Key Design Patterns

- **Strategy Pattern**: Pluggable authentication providers and payload formatters
- **Factory Pattern**: Scenario runner selection based on test level
- **Observer Pattern**: Real-time monitoring and reporting
- **Template Method**: Base classes for common functionality

## Configuration Files

**Test Scenarios:** YAML files in `tests/` directory
- Define test cases with authentication, test level, steps, and assertions
- Support environment variable substitution with `{{ env.VAR_NAME }}`

**Project Configuration:** `pyproject.toml`
- Build system and dependencies
- Tool configurations (black, isort, mypy)
- Package metadata and CLI entry points

## Important Notes

- All models use Pydantic for validation and serialization
- Type hints required throughout (mypy strict mode)
- Error handling includes retries and timeout management
- The `test` model in PydanticAI doesn't require API keys for development
- Session management is more efficient than full conversation history for stateful APIs
- Goal evaluation with intelligent mode reduces false positives from keyword matching

**Browser Mode:**
- Requires `playwright install` to download browser binaries
- Supabase service role keys are admin-level - never commit them to repos
- Screenshot evaluation requires vision-capable models (GPT-4o, Claude 3.5 Sonnet, etc.)
- Use `dom_then_screenshot` evidence mode for best cost/accuracy balance
- Browser traces can be viewed with `playwright show-trace trace.zip`
- For a visible browser locally, set `browser.headless: false`; keep `headless: true` in CI/CD
- Magic link auth auto-generates unique emails (`replicantx+<uuid>@replicantx.org`) when `user_mode: generated`
