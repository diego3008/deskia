# Agents.md

This file provides guidance to Codex when working with code in this repository.

## Project Overview

Booker is an agentic AI project intended to automate the process of appointment booking of
businesses that provide services to their clients this way.

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

**LangGraph config** (`langgraph.json`): maps graph names to their Python module paths and sets the env file. Add new graphs here to expose them via the API.

## Environment Variables

Required in `.env`:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY` + `LANGCHAIN_TRACING_V2` + `LANGCHAIN_PROJECT`
- `BOT_TOKEN` (Telegram bot)
- `OPENROUTER_API_KEY`
- `LANGSMITH_TRACING`
- `LANGSMITH_WORKSPACE_ID`
- `LANGSMITH_PROJECT`
- `LANGSMITH_ENDPOINT`

> **Warning**: The current `.env` file contains live API keys and is not gitignored. Add `.env` to `.gitignore` and rotate any exposed keys.
> **Warning**: Do not start testing processes when implementing a plan or feature. Always ask for authorization before doing it.
