# Contributing to SSM Explorer

Thank you for your interest in contributing! This is part of the **Douklar DevOps Tools** series.

## Development Setup

```bash
# Clone and install
git clone https://github.com/<your-org>/ssm-explorer.git
cd ssm-explorer
poetry install

# Install pre-commit hooks
poetry run pre-commit install

# Run the CLI
poetry run ssm-explorer --help
```

## Running Tests

```bash
# Full test suite
poetry run pytest

# With coverage
poetry run pytest --cov=ssm_explorer

# Single test file
poetry run pytest tests/test_config.py
```

## Code Quality

```bash
# Lint
poetry run ruff check src/

# Format
poetry run ruff format src/

# Type check
poetry run mypy src/
```

## Commit Convention

This project uses **[Conventional Commits](https://www.conventionalcommits.org/)** for automated versioning.

Every commit message must follow this format:

```
<type>: <short description>

[optional body]
```

### Types and Version Impact

| Type | Version Bump | Example |
|:---|:---|:---|
| `fix:` | Patch (1.0.0 → 1.0.1) | `fix: handle empty path in deepsearch` |
| `feat:` | Minor (1.0.0 → 1.1.0) | `feat: add CSV export format` |
| `feat!:` | Major (1.0.0 → 2.0.0) | `feat!: rename --filter to --grep` |
| `docs:` | No release | `docs: update README examples` |
| `chore:` | No release | `chore: update dev dependencies` |
| `refactor:` | No release | `refactor: simplify config resolution` |
| `test:` | No release | `test: add diff command edge cases` |

### Breaking Changes

Add `BREAKING CHANGE:` in the commit body or append `!` after the type:

```
feat!: rename --filter-path to --grep

BREAKING CHANGE: The --filter-path flag has been renamed to --grep.
```

## Pull Requests

1. Create a feature branch from `main`
2. Make your changes with conventional commit messages
3. Ensure all checks pass: `poetry run pytest && poetry run ruff check src/ && poetry run mypy src/`
4. Open a PR against `main`
5. On merge, `python-semantic-release` will automatically version and release if needed

## Security

- **Never** commit real AWS credentials, secrets, or internal infrastructure names
- Use placeholders like `my_profile_aws`, `/my/app/prod` in examples
- The tool is strictly **read-only** — no AWS write operations

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
