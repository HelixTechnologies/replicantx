# ReplicantX

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

**ReplicantX** is an end-to-end testing harness for AI agents that communicates via web service APIs. It enables you to run comprehensive test scenarios against live HTTP APIs with support for multiple authentication methods and detailed reporting.

## ✨ Features

- **Two Test Levels**: 
  - **Level 1 (Basic)**: Fixed user messages with deterministic assertions
  - **Level 2 (Agent)**: Intelligent Replicant agent with configurable facts and conversation goals
- **Pydantic-Based Replicant Agent**: Smart conversational agent that acts like a real user
- **Configurable Facts & Behavior**: Agents can have knowledge (Name, Preferences) and custom personalities
- **Real-time Monitoring**: Watch mode (`--watch`) for live conversation monitoring
- **Technical Debugging**: Debug mode (`--debug`) with detailed HTTP, validation, and AI processing logs
- **Multiple Authentication**: Supabase email+password, custom JWT, or no-auth
- **CLI Interface**: Easy-to-use command-line interface with `replicantx run`
- **Automatic .env Loading**: No manual environment variable sourcing required
- **GitHub Actions Ready**: Built-in workflow for PR testing with Render preview URLs
- **Rich Reporting**: Markdown and JSON reports with timing and assertion results
- **Retry & Backoff**: Robust HTTP client with automatic retry logic

## 🚀 Quick Start

### Installation

```bash
pip install replicantx[cli]
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
SUPABASE_ANON_KEY=your-supabase-key
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
   - `SUPABASE_ANON_KEY` = `your-supabase-key`
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
- 👤 **User messages** as they're sent (with timestamps)
- ⏱️ **Response waiting indicators**
- 🤖 **Assistant responses** as received
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
[22:04:42] 👤 User: Hi, I'd like to book a flight to Paris.
[22:04:52] ✅ Step 1: PASSED (10.2s)
[22:04:52] 🤖 Assistant: What cabin class would you prefer?
[22:04:53] 👤 User: Business class, please.
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
    budget: "$3000"
    preferences: "aisle seat, vegetarian meal"
  system_prompt: |
    You are a customer trying to book a flight to Paris. You have all 
    the necessary information but you're a typical user who doesn't 
    provide all details upfront. You're polite and conversational.
  initial_message: "Hi, I'd like to book a flight to Paris for next weekend."
  max_turns: 15
  completion_keywords: ["booked", "confirmed", "reservation number"]
  llm:
    model: "anthropic:claude-3-5-sonnet-latest"  # PydanticAI model string
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