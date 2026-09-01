# Thread Context Compaction

## Purpose

Long conversations can make an agent slower, more expensive, and easier to
derail with stale context. The compaction feature keeps one stable LangGraph
`thread_id` while shrinking the message state used by later model calls.

The thread remains the durable conversation identity. Compaction is only a
context-management operation; it does not start a new thread.

## Runtime flow

The parent graph runs compaction before the first model-backed node:

```text
incoming message
      |
message_listener
      |
compact_context_node
      |
message_categorizer
      |
user-services / appointment-services / writer / fallback
```

The node is registered as `should_compact` in
`src/graph/appointment_booking_graph.py`. Every subsequent branch receives the
same compacted state for the current invocation.

## Trigger policy

`compact_context_node` uses LangChain's
`count_tokens_approximately` rather than counting messages. It counts the
current messages plus the existing summary, then adds a fixed allowance for
system prompts and tool instructions.

Current constants:

| Constant | Value | Meaning |
| --- | ---: | --- |
| `COMPACT_AT_TOKENS` | `12_000` | Start compaction at this estimated context size |
| `PROMPT_TOKEN_ALLOWANCE` | `2_000` | Reserve for prompts and tool instructions |
| `KEEP_RECENT_MESSAGES` | `6` | Keep the newest messages verbatim |

The values are intentionally centralized at the top of
`src/nodes/compact_context_node.py` so they can be calibrated from production
token and latency metrics later.

## What gets summarized

When the threshold is reached, the node selects the oldest messages outside
the recent tail. The cut point is moved backward until it starts on a
`HumanMessage`, so the summarized prefix contains complete earlier turns. This
also avoids splitting an active tool-call sequence between the summarized and
verbatim portions.

The summarizer receives:

1. The previous `conversation_summary`, if one exists.
2. The selected older messages formatted as `User:` and `Agent:` lines.

The summarizer is instructed to preserve:

```text
Customer facts:
Conversation goal:
Decisions and commitments:
Completed actions:
Unresolved questions:
```

The result is stored in `MessageGraphState.conversation_summary`. Older
messages are removed from the current `messages` channel with LangGraph
`RemoveMessage` updates. The latest six messages remain available verbatim.

## Structured state remains authoritative

The summary is narrative context, not a source of truth for actions. Booking
and customer fields remain separate state values, including:

- `customer_id` and `customer`
- `current_flow`
- `pending_question`
- `next_action`
- `active_appointment`
- `confirmed_slot`

This prevents a model-generated summary from replacing the exact values used
by routing and appointment tools.

## How models receive the summary

The summary is included in every existing model path:

- `build_recent_history(messages, summary)` prepends it for the categorizer,
  services planner, and message writer.
- `customer_node`, `enquiry_node`, and `services_request_node` add it as a
  `SystemMessage` before the remaining conversation messages.

The customer-validation subgraph declares `conversation_summary` in
`UserValidationState`, so the parent graph does not lose the summary when
entering that subgraph.

## Failure and edge behavior

- Below the threshold: the node returns `{}` and state is unchanged.
- Fewer than enough messages to form an older complete turn: no compaction is
  performed.
- A message without an ID: no compaction is performed because it cannot be
  safely removed with `RemoveMessage`.
- Summarizer exception or empty output: the selected old messages are removed
  without replacing the summary. This is a deliberately lossy fallback; the
  backend should retain the raw transcript separately for audit and recovery.

## Operating requirements

1. Use the same `thread_id` for every message in one customer conversation.
2. Run with LangGraph persistence/checkpointing enabled so state and
   `conversation_summary` survive between invocations.
3. Keep the backend's raw message ledger if support, audit, or replay requires
   the uncompressed transcript.
4. Monitor summarizer latency, failures, and token counts before changing the
   constants.

## Verification

The focused compaction tests cover summary creation, removal of the old
prefix, recent-tail preservation, and summary delivery to the writer. The
repository suite currently passes with:

```bash
.venv/bin/python -m unittest discover -s tests
```

