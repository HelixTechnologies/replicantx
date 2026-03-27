# AGENTS.md

This file provides repository guidance for coding agents working in this repo.

## Project Overview

**ReplicantX** is an end-to-end testing harness for AI agents that communicate via HTTP APIs or web browsers. It supports deterministic API checks, intelligent Replicant-driven flows, browser automation with Playwright, structured reporting, and standalone browser issue triage/autofiling.

**Stack**: Python 3.11+, Pydantic v2, PydanticAI, httpx, Typer, Rich, Playwright

Useful references:
- [README.md](README.md)
- [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md)
- [docs/browser-mode-config.md](docs/browser-mode-config.md)

## Common Commands

### Setup

```bash
pip install -e ".[dev]"
playwright install
```

### Quality

```bash
black replicantx/
isort replicantx/
mypy replicantx/
```

### Tests

```bash
pytest
pytest tests/test_issue_reporting.py tests/test_json_reporter.py tests/test_browser_identity_extraction.py
```

### CLI

```bash
replicantx validate tests/*.yaml
replicantx run tests/*.yaml
replicantx run tests/*.yaml --report report.md
replicantx run tests/*.yaml --debug --watch
replicantx run tests/*.yaml --parallel --max-concurrent 3
```

### Browser Mode

```bash
# Watch a real browser window
# set replicant.browser.headless: false in YAML first
replicantx run tests/browser_test.yaml --watch

# Write local issue drafts only
replicantx run tests/browser_test.yaml --issue-mode draft-only --issue-artifact-upload off

# Auto-file high-confidence issues
replicantx run tests/browser_test.yaml --issue-mode auto-high-confidence --issue-repo HelixTechnologies/helix-agent

# View retained traces
playwright show-trace artifacts/trace.zip
```

## Architecture

Core areas:
- `replicantx/cli.py`: Typer CLI entry point
- `replicantx/models.py`: Pydantic config/result models
- `replicantx/scenarios/basic.py`: Level 1 deterministic scenarios
- `replicantx/scenarios/agent.py`: Level 2 API-mode Replicant scenarios
- `replicantx/scenarios/browser_agent.py`: Level 2 browser-mode runner
- `replicantx/scenarios/replicant.py`: core Replicant logic and goal evaluation
- `replicantx/auth/`: pluggable authentication providers
- `replicantx/reporters/`: markdown/json reporters
- `replicantx/tools/browser/`: Playwright observation, actions, artifacts, lifecycle
- `replicantx/issue_reporting.py`: standalone browser issue classification, bundle generation, artifact upload, Logfire enrichment, and GitHub filing

## Browser Issue Reporting

Issue reporting is controlled from the CLI, not the scenario YAML.

CLI options:
- `--issue-mode off|draft-only|auto-high-confidence`
- `--issue-repo owner/name`
- `--issue-artifact-upload on|off`
- `--issue-output <dir>`
- `--logfire-config <path>`

Behavior:
- Browser runs continue when first-party `401`, `403`, `5xx`, console errors, or page errors occur, as long as the Replicant can still make progress.
- A scenario can pass and still emit an issue bundle or GitHub issue for a non-blocking bug.
- Classification outcomes are `auto_file`, `review`, and `skip`.
- `auto-high-confidence` only files `auto_file` cases; all processed cases still get local issue artifacts.

Generated artifacts:
- `issue_bundle.json`
- `issue.md`
- referenced screenshots and traces from the scenario artifact directory

## Environment Variables

LLM providers:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `GROQ_API_KEY`

Auth and target config:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REPLICANTX_TARGET`
- `JWT_TOKEN`

Browser issue reporting:
- `REPLICANTX_GITHUB_TOKEN`
- `REPLICANTX_LOGFIRE_API_KEY`
- `REPLICANTX_LOGFIRE_BASE_URL`
- `REPLICANTX_LOGFIRE_SERVICE_NAME`
- `REPLICANTX_LOGFIRE_CONFIG`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REPLICANTX_ARTIFACT_BUCKET`
- `REPLICANTX_ARTIFACT_SIGNED_URL_TTL_SECONDS`
- `REPLICANTX_ENVIRONMENT`

YAML interpolation uses `{{ env.VARIABLE_NAME }}`.

## Notes For Agents

- Prefer `rg` for search.
- Use `apply_patch` for file edits.
- Do not assume browser issue signals are blocking user-visible failures.
- When working on browser issue reporting, keep the local bundle format reusable outside GitHub Actions.
- The default repo-level Logfire query config path is `replicantx.logfire.yaml` or `replicantx.logfire.yml`.
