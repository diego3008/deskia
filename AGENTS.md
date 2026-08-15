# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project Overview

Deskia is an AI agent designed to perform multiple tasks for busineses that provide services to their
clients making appointments such as barber shops, nail bars, dental clinics, etc.

## Commands

This project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync

# Run the LangGraph development server (hot reload, Studio UI at localhost:8123)
langgraph dev

# Run with Docker (production-like)
langgraph up

# Run the entry point directly
uv run python main.py
```

## Architecture

**State** (`src/state.py`): `AgentState` is a `TypedDict` with:

- `messages`: annotated with `add_messages` reducer (appends, not overwrites)
- `user_id`: str
- `iteration_count`: int

**Graph entrypoint** (`src/graph/email_graph.py`): exports `emailSupportGraph`, registered in `langgraph.json` as the `email_support` graph.

**LangGraph config** (`langgraph.json`): maps graph names to their Python module paths and sets the env file. Add new graphs here to expose them via the API.

## Key Dependencies

- `langgraph` + `langgraph-api`: graph execution and REST API serving
- `langchain-anthropic` / `langchain-openai` / `langchain-aws`: LLM providers
- `langsmith`: tracing (configured via `LANGCHAIN_TRACING_V2=true`, project `deskia`)

## Environment Variables

Required in `.env`:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY` + `LANGCHAIN_TRACING_V2` + `LANGCHAIN_PROJECT`
- `BOT_TOKEN` (Telegram bot)

> **Warning**: The current `.env` file contains live API keys and is not gitignored. Add `.env` to `.gitignore` and rotate any exposed keys.
