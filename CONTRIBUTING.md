# Contributing to ReplicantX

Thank you for your interest in contributing to ReplicantX! This document provides guidelines and best practices for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Creating Issues](#creating-issues)
- [Making Changes](#making-changes)
- [Code Style and Standards](#code-style-and-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Review Process](#review-process)
- [Release Process](#release-process)

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- A GitHub account

### Setting Up Your Development Environment

1. **Fork the Repository**
   ```bash
   # Navigate to https://github.com/HelixTechnologies/replicantx
   # Click the "Fork" button in the top-right corner
   ```

2. **Clone Your Fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/replicantx.git
   cd replicantx
   ```

3. **Add the Upstream Remote**
   ```bash
   git remote add upstream https://github.com/HelixTechnologies/replicantx.git
   ```

4. **Install Development Dependencies**
   ```bash
   pip install -e .
   pip install -r requirements.txt  
   ```

5. **Verify Installation**
   ```bash
   python -m replicantx.cli --version
   ```

## Development Workflow

### 1. Keep Your Fork Updated

Before starting any new work, ensure your fork is up to date:

```bash
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

### 2. Create a Feature Branch

Always work on a new branch for your changes:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
# or
git checkout -b docs/your-documentation-update
```

### Branch Naming Conventions

- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `test/` - Test improvements or additions
- `refactor/` - Code refactoring
- `chore/` - Maintenance tasks

Examples:
- `feature/add-parallel-execution`
- `fix/goal-evaluation-logic`
- `docs/update-contributing-guidelines`
- `test/add-integration-tests`

## Creating Issues

### Before Creating an Issue

1. **Search existing issues** to avoid duplicates
2. **Check the documentation** to see if your question is already answered
3. **Reproduce the issue** if it's a bug

### Issue Templates

When creating an issue, use the appropriate template:

#### Bug Report
- **Clear description** of the bug
- **Steps to reproduce** the issue
- **Expected vs actual behavior**
- **Environment details** (OS, Python version, etc.)
- **Minimal test case** if applicable

#### Feature Request
- **Clear description** of the feature
- **Use case** and motivation
- **Proposed implementation** (if you have ideas)
- **Alternative solutions** considered

#### Documentation Issue
- **What's missing or unclear**
- **Where it should be added**
- **Suggested content**

## Making Changes

### Code Style and Standards

#### Python Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Use type hints for function parameters and return values
- Keep functions focused and under 50 lines when possible
- Use descriptive variable and function names

#### Commit Message Guidelines

Use conventional commit format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(cli): add parallel execution support

fix(agent): correct goal evaluation logic

docs(readme): update installation instructions

test(scenarios): add integration tests for auth providers
```

### Making Your Changes

1. **Make focused, atomic commits**
   ```bash
   git add .
   git commit -m "feat(agent): add intelligent goal evaluation"
   ```

2. **Keep commits small and focused**
   - One logical change per commit
   - Don't mix different types of changes
   - Use meaningful commit messages

3. **Test your changes**
   ```bash
   # Run the test suite
   python -m pytest tests/
   
   # Run specific tests
   python -m replicantx.cli run tests/your-test.yaml
   
   # Run with different options
   python -m replicantx.cli run tests/ --debug --watch
   ```

## Testing

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=replicantx

# Run specific test files
python -m pytest tests/test_scenarios.py

# Run ReplicantX scenarios
python -m replicantx.cli run tests/*.yaml
```

### Writing Tests

- Write tests for new features
- Ensure existing tests still pass
- Add integration tests for complex scenarios
- Test both success and failure cases

### Test Scenarios

When adding new test scenarios:

1. Create YAML files in the `tests/` directory
2. Use descriptive names that explain the test purpose
3. Include both basic and replicant agent scenarios
4. Test different authentication methods
5. Test edge cases and error conditions

## Submitting Changes

### 1. Push Your Branch

```bash
git push origin feature/your-feature-name
```

### 2. Create a Pull Request

1. Go to your fork on GitHub
2. Click "Compare & pull request" for your branch
3. Fill out the pull request template
4. Add appropriate labels
5. Request reviews from maintainers

### Pull Request Guidelines

#### Title
Use the same format as commit messages:
```
feat(cli): add parallel execution support
```

#### Description
Include:
- **Summary** of changes
- **Motivation** for the change
- **Testing** performed
- **Breaking changes** (if any)
- **Related issues** (use `Fixes #123` or `Closes #123`)

#### Example PR Description
```markdown
## Summary
Adds parallel execution support to the CLI, allowing multiple scenarios to run concurrently.

## Motivation
Running scenarios sequentially can be slow for large test suites. Parallel execution significantly reduces total execution time.

## Changes
- Added `--parallel` and `--max-concurrent` CLI options
- Implemented `run_scenarios_parallel()` function
- Added `parallel: bool` field to ScenarioConfig
- Updated documentation with usage examples

## Testing
- Added unit tests for parallel execution logic
- Tested with 10 concurrent scenarios
- Verified proper error handling and cleanup
- Confirmed no regression in sequential execution

## Breaking Changes
None - all changes are backward compatible.

Fixes #45
```

## Review Process

### What Reviewers Look For

1. **Code Quality**
   - Follows style guidelines
   - Proper error handling
   - Good documentation

2. **Functionality**
   - Works as intended
   - Handles edge cases
   - Doesn't break existing features

3. **Testing**
   - Adequate test coverage
   - Tests pass
   - New scenarios work correctly

### Responding to Review Comments

1. **Address all comments** before requesting re-review
2. **Make additional commits** if needed
3. **Explain your reasoning** if you disagree
4. **Ask for clarification** if something is unclear

### Getting Your PR Merged

- All tests must pass
- Code review must be approved
- Documentation must be updated
- No merge conflicts

## Release Process

### Version Bumping

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

Before a release:
- [ ] All tests pass
- [ ] Documentation is updated
- [ ] Version is bumped in `pyproject.toml`
- [ ] CHANGELOG.md is updated
- [ ] Release notes are prepared

## Getting Help

### Communication Channels

- **GitHub Issues**: For bugs, feature requests, and questions
- **GitHub Discussions**: For general questions and community discussion
- **Pull Requests**: For code reviews and technical discussions

## Recognition

Contributors will be recognized in:
- The project's README.md
- Release notes
- GitHub contributors page

Thank you for contributing to ReplicantX! 🚀 