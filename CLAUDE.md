# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ReplicantX** is an end-to-end testing harness for AI agents that communicate via HTTP APIs. It enables comprehensive testing of conversational AI systems with support for intelligent agents, multiple authentication methods, and detailed reporting.

**Stack**: Python 3.11+, Pydantic v2, PydanticAI, httpx, Typer, Rich
**Structure**: Modular architecture with pluggable auth, payload formatters, and reporters

📖 **For detailed architecture and module documentation, see [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md)**

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
│   ├── agent.py        # Intelligent agent scenarios (Level 2)
│   └── replicant.py    # Core Replicant agent implementation
├── auth/               # Authentication providers
│   ├── base.py         # Base authentication class
│   ├── supabase.py     # Supabase auth implementation
│   ├── jwt.py          # JWT token auth
│   └── noop.py         # No authentication
├── reporters/          # Output formatters
│   ├── markdown.py     # Markdown report generation
│   └── json.py         # JSON report generation
└── tools/              # Utility modules
    ├── http_client.py  # HTTP client with retry logic
    ├── payload_formatter.py  # API payload format support
    └── session_manager.py    # Session management
```

### Test Levels

**Level 1 (Basic):** Fixed user messages with deterministic assertions
- Defined in `scenarios/basic.py`
- Simple step-by-step conversations
- Assertions: `expect_contains`, `expect_regex`, `expect_equals`, `expect_not_contains`

**Level 2 (Agent):** Intelligent AI-powered Replicant agents
- Defined in `scenarios/agent.py` and `scenarios/replicant.py`
- Uses PydanticAI for LLM integration
- Configurable facts, goals, and personalities
- Goal evaluation with intelligent analysis

### Authentication System

Pluggable authentication providers in `auth/`:
- **noop**: No authentication (default)
- **supabase**: Supabase email/password authentication
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

### Environment Variables

ReplicantX automatically detects environment variables from `.env` files and system environment:

**LLM Integration:**
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GOOGLE_API_KEY`: Google AI API key
- `GROQ_API_KEY`: Groq API key

**Supabase Authentication:**
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_ANON_KEY`: Supabase anonymous key

**Target API:**
- `REPLICANTX_TARGET`: Target API domain
- `JWT_TOKEN`: JWT token for authentication

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
