# AGENTS.md — My Personal Dev Setup

This project serves as a self-hosted coding agent orchestrator.
It manages itself via the same Spec-Kit workflow it runs for other projects.

## Stack

- Python 3.11+
- FastAPI + uvicorn (webhook receiver)
- LangGraph (workflow orchestration)
- SQLite (state + traces persistence)
- httpx (GitHub API calls)
- uv (package management — never use pip directly)

## Architecture

```
api/          Webhook receiver and event router
graph/        LangGraph state machine (nodes, edges, state)
github/       GitHub API wrapper
agent/        OpenCode invocation and prompt templates
traces/       Trace event logging and quality scoring
persistence/  LangGraph SQLite checkpointer setup
config/       Settings (pydantic-settings, .env)
tests/        pytest unit tests
```

## Conventions

- Async everywhere — all I/O uses async/await
- Type hints required on all function signatures
- No bare `except` — always catch specific exceptions
- Log at INFO for normal operations, ERROR for failures
- All GitHub API calls go through `github/client.py` — never call httpx directly in nodes
- All OpenCode invocations go through `agent/runner.py` — never call subprocess directly in nodes
- Prompts are templates in `agent/prompts/` — never inline prompts in nodes

## Testing

```bash
uv run pytest
```

All tests must pass before committing.
Tests use mocks for GitHub API and OpenCode — no real network calls in tests.

## Running locally

```bash
uv run uvicorn api.main:app --port 8080 --reload
```
