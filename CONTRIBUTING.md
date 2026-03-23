# Contributing to tablestakes

Thanks for your interest in contributing! We welcome bug fixes, new features, and improvements.

For clear bug fixes or typos, just submit a PR. For new features or architectural changes, open an issue first to discuss.

## Setup

```bash
git clone https://github.com/oborchers/tablestakes.git
cd tablestakes
make init        # creates venv, installs deps, sets up pre-commit hooks
```

Requires [uv](https://docs.astral.sh/uv/). All commands use `uv run` — never use `python` or `pip` directly.

## Running Checks

```bash
make check       # lint + typecheck + tests (run before every PR)
make format      # auto-format code
make test-cov    # tests with coverage report
```

## Architecture

The codebase has four layers:

1. **Parser** (`parser.py`) — detects and classifies tables in Markdown files
2. **Converter** (`converter.py`) — bidirectional HTML/pipe table conversion
3. **Hasher** (`hasher.py`) — content hashing for optimistic concurrency
4. **Tools** (`tools/`) — MCP tool implementations using `_safe_write` for all writes

All write operations go through a single code path (`_safe_write`) that enforces the shifted-lines safety model.

## PR Guidelines

- Keep PRs focused — one feature or one fix per PR
- All checks must pass (`make check`)
- New code needs tests — target 85%+ coverage
- Follow existing code style — Ruff enforces this automatically via pre-commit

## Reporting Issues

Use [GitHub Issues](https://github.com/oborchers/tablestakes/issues). For security vulnerabilities, see [SECURITY.md](SECURITY.md).
