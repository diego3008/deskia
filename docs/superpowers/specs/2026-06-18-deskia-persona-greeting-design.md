# Deskia Persona & Greeting Response Design

**Date:** 2026-06-18  
**Status:** Approved

## Overview

Add the Deskia persona to the agent so it never identifies as Claude, and wire up the existing `message_writer` to generate dynamic replies. On the first message of a conversation the reply opens with a greeting introducing Deskia by name. All replies adapt in tone and format to the detected message category.

## Graph Changes

Current pipeline:
```
START → message_listener → message_categorizer → END
```

New pipeline:
```
START → message_listener → message_categorizer → message_writer → END
```

No new state fields are required. First-message detection is derived inline:
```python
is_first_message = sum(1 for m in state["messages"] if isinstance(m, HumanMessage)) == 1
```

## State

`MessageGraphState` in `src/state.py` is unchanged. The existing `message_response: str` field receives the writer output. `OutBoundsMessge` (existing TypedDict) is used as structured output.

## Prompts

### `src/prompts/agents.py`
Add `MESSAGE_WRITER_AGENT` establishing the Deskia persona:
- Name: Deskia
- Role: AI customer support assistant for a SaaS AI consultancy
- Constraint: never identify as Claude or any other AI brand

### `src/prompts/tasks.py`
Add `WRITER_TASK` with input variables `{message_category}`, `{message_content}`, `{is_first_message}`:
- If `is_first_message` is true: open with a warm greeting introducing Deskia by name and ask "What can I do for you?" before addressing the message
- Tone/format by category:
  - `inquiry` → informative and helpful
  - `customer_complaint` → empathetic and solution-focused
  - `customer_feedback` → appreciative and constructive
  - `unrelated` → politely redirect to supported topics

### `src/prompts/__init__.py`
Add `MESSAGE_WRITER_PROMPT = MESSAGE_WRITER_AGENT + "\n\n" + WRITER_TASK`, following the existing categorizer pattern.

## Agent

`src/agents/message_writer.py` (refactor existing stub):
- Model: `claude-haiku-4-5-20251001`, `temperature=0`
- `PromptTemplate` inputs: `message_category`, `message_content`, `is_first_message`
- Structured output: `OutBoundsMessge`
- Returns a `message_writer()` factory function

## Node

`src/nodes/message_writer_node.py` (new file):
- Reads `state["current_message"]` and `state["message_category"]`
- Derives `is_first_message = len(state["messages"]) == 1`
- Invokes `message_writer()` with the three inputs
- Writes result to `state["message_response"]`
- Appends an `AIMessage` with the response text to `state["messages"]`

`src/nodes/__init__.py`: register `"message_writer"` → `message_writer_node`.

## Graph Wiring

`src/graph/message_receiver_graph.py`:
- `add_node("message_writer", NODES["message_writer"])`
- Replace `add_edge("category", END)` with `add_edge("category", "message_writer")` + `add_edge("message_writer", END)`

## Files Touched

| File | Change |
|------|--------|
| `src/prompts/agents.py` | Add `MESSAGE_WRITER_AGENT` |
| `src/prompts/tasks.py` | Add `WRITER_TASK` |
| `src/prompts/__init__.py` | Export `MESSAGE_WRITER_PROMPT` |
| `src/agents/message_writer.py` | Refactor to use new prompt + structured output |
| `src/nodes/message_writer_node.py` | New node |
| `src/nodes/__init__.py` | Register new node |
| `src/graph/message_receiver_graph.py` | Add node + edges |

## Out of Scope

- Telegram send/receive integration (separate concern)
- Multi-turn memory or session storage
- Per-business configurability of the persona
