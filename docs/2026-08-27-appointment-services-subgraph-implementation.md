# Appointment Services Subgraph — Implementation Breakdown

Date: 2026-08-27  
Feature range: `82cf5fb..2dfc75b`  
Related plan: [Appointment Services Subgraph plan](superpowers/plans/2026-08-27-appointment-services-subgraph.md)

## Summary

This change adds an appointment-specific ReAct subgraph and connects it to the existing validated-customer workflow. The customer is identified or created first, then the appointment agent can call the existing availability, booking, lookup, and rescheduling tools through LangGraph's `ToolNode`.

The implementation deliberately reuses the existing nodes, state schema, and API tools. It does not add another agent framework, planner, dependency, or duplicate API layer.

## Resulting workflow

```text
Incoming message
      |
message_listener
      |
message_categorizer
      |
      +-- customer validation is pending ------> user_services_validation
      |                                                |
      |                                      customer validated
      |                                                |
      +-- appointment intent + no customer ---> user_services_validation
      |                                                |
      |                                                v
      +-- appointment intent + customer ------> appointment_services
                                                       |
                                              appointment_agent
                                                       |
                                          tool call? --+-- no --> END
                                                       |
                                                      yes
                                                       v
                                                    ToolNode
                                                       |
                                                       +----> appointment_agent

appointment_services --> message_writer --> END
```

The `appointment_agent` decides which tool is needed and supplies its arguments. `ToolNode` is the only node that executes those tools. This separation is important: a `ToolNode` cannot start the workflow by itself because it expects an `AIMessage` that already contains a tool call.

## Changes and reasons

### 1. Exposed the validated customer in shared graph state

Files:

- [`src/state.py`](../src/state.py)
- [`src/nodes/user_services_validation/customer_lookup_node.py`](../src/nodes/user_services_validation/customer_lookup_node.py)
- [`src/nodes/user_services_validation/customer_creation_node.py`](../src/nodes/user_services_validation/customer_creation_node.py)

Changes:

- Added `customer` and `customer_id` to `UserValidationState`.
- Allowed `current_flow` to be `None`, because successful and explicitly exited workflows clear it.
- On a successful customer lookup or creation, copied the returned customer and ID into top-level graph state.
- Retained the existing `user_data["customer"]` value for compatibility with the validation workflow.
- Treated a non-object response or a customer object without an `id` as a validation failure and used the existing retry path.

Why:

LangGraph subgraphs only hand back fields declared in their state contract. Keeping the customer solely inside `user_data` made the identity unavailable to the parent appointment graph and its tools. Publishing `customer_id` at the boundary gives appointment operations one stable identity field while preserving existing consumers.

The response-shape checks also protect the graph from a successful HTTP response containing malformed JSON. Without them, calling `.get("id")` on a list or scalar could crash the workflow or allow an unidentified customer into an appointment write.

### 2. Decoupled RAG initialization from customer validation imports

File:

- [`src/nodes/user_services_validation/services_inquiry_node.py`](../src/nodes/user_services_validation/services_inquiry_node.py)

Changes:

- Removed eager global construction of `rag_tool` during module import.
- Moved Chroma and other heavy RAG dependencies into the builder function.
- Added a process-local, lock-protected `get_rag_tool()` singleton.
- Initialized the singleton and executed synchronous retrieval in worker threads.

Why:

Importing the customer-validation package previously initialized embeddings and the RAG stack immediately, even when running an unrelated appointment path or test. Under LangGraph's blocking-call detection, even importing Chroma could fail while its dependencies scanned package files. Lazy imports and `asyncio.to_thread()` keep that work off the event loop, while the singleton prevents rebuilding and re-embedding the catalog for every request.

This is still only an initialization and execution-boundary fix. The RAG retrieval strategy itself was intentionally left unchanged.

### 3. Added the appointment ReAct tool loop

File:

- [`src/graph/appointment_services_subgraph.py`](../src/graph/appointment_services_subgraph.py)

Changes:

- Built the subgraph with the shared `MessageGraphState`.
- Added `appointment_agent` using the existing `services_request_node`.
- Added `tools` using `ToolNode(tools)` and the existing appointment tool list.
- Added the loop `appointment_agent -> tools -> appointment_agent`.
- Used `tools_condition` to finish when the agent returns a response without another tool call.
- Exported a compiled `appointment_services_subgraph` instance.

Why:

The agent and tool executor have different jobs:

- `appointment_agent` interprets the conversation, selects a tool, and creates the tool call.
- `ToolNode` executes the selected function, including the HTTP request and any state update returned through `Command`.

This follows LangGraph's standard tool-loop pattern and keeps API execution in the `tools` node, as required. The node was named `appointment_agent` rather than `appointment_service` to make that role explicit.

### 4. Routed validated customers into appointment services

File:

- [`src/graph/appointment_booking_graph.py`](../src/graph/appointment_booking_graph.py)

Changes:

- Registered `appointment_services` in the parent graph.
- Added routing for new and rescheduled appointment categories.
- Added `_has_validated_customer`, accepting either top-level `customer_id` or `customer.id`.
- Sent unidentified appointment customers through `user_services` first.
- Added a conditional handoff from `user_services` to `appointment_services` after validation succeeds.
- Kept retry actions and pending validation questions in `user_services`, even if the latest short reply is categorized differently.
- Routed greetings, complaints, feedback, and declines directly to the writer.
- Kept cancellation and service inquiry on the existing user-services path.
- Routed appointment completion through the message writer before ending the parent graph.

Why:

Customer validation and appointment operations are separate responsibilities, but they must behave as one continuous conversation. The parent graph is the correct place to enforce the handoff:

1. detect an appointment workflow;
2. validate or create the customer if needed;
3. enter appointment services only after an ID exists;
4. preserve the appointment flow over short follow-up messages.

Giving pending validation state priority prevents replies such as an email address, a confirmation, or customer details from being mistaken for a new intent.

### 5. Made appointment-flow entry and exit explicit

File:

- [`src/nodes/message_categorizer_node.py`](../src/nodes/message_categorizer_node.py)

Changes:

- Replaced stale `active_flow` and `service_request` references with the actual state names and categories used by the graph.
- Set `current_flow = "appointment_services"` for new and rescheduled appointment intents.
- Cleared appointment and validation continuity fields on explicit exit intents such as greeting, complaint, feedback, decline, and cancellation.
- Removed an unused model import.

Why:

`current_flow` lets follow-up messages such as “at 3 PM” remain in the appointment workflow without requiring the classifier to repeat the original category. Conversely, explicit exits must clear both appointment and validation state. In particular, a decline such as “No, gracias” must not be interpreted as a customer name by a pending customer-creation step.

### 6. Cleared workflow state only after successful writes

File:

- [`src/nodes/tools/services/services_tools.py`](../src/nodes/tools/services/services_tools.py)

Changes:

- After successful booking, cleared `confirmed_slot`, `current_flow`, `next_action`, and `pending_question`.
- After successful rescheduling, also cleared `active_appointment`.
- Left availability checks and appointment lookup state intact.

Why:

Availability and lookup are intermediate operations, so their state is needed by the next tool call. Booking and rescheduling are terminal writes, so retaining their workflow state would incorrectly route the customer's next message back into a completed appointment flow or reuse a stale slot or appointment.

The existing guards remain in place:

- booking requires availability confirmation for the exact requested start time;
- rescheduling requires both a selected appointment and confirmation of the new slot.

### 7. Prevented duplicate assistant responses

File:

- [`src/nodes/message_writer_node.py`](../src/nodes/message_writer_node.py)

Change:

- If the latest message is already a final `AIMessage` without tool calls, the writer reuses its content as `message_response` instead of invoking the writer model and appending another assistant message.

Why:

After the final tool result, `appointment_agent` already produces the customer-facing answer. Running a second model over that answer duplicated or rephrased it and added two assistant messages for one turn. The guard keeps one final response while preserving the normal writer path for validation prompts, greetings, and other nodes that have not produced a final AI response.

### 8. Added focused integration and regression coverage

Files:

- [`tests/test_appointment_services_subgraph.py`](../tests/test_appointment_services_subgraph.py)
- [`tests/test_pending_question_flow.py`](../tests/test_pending_question_flow.py)

Coverage added:

- Customer lookup and creation publish `customer` and `customer_id`.
- Malformed customer API payloads enter retry state rather than crashing.
- The appointment graph contains the expected agent/tool loop.
- A compiled subgraph can execute a real `ToolNode` with a deterministic fake model and fake HTTP client.
- Parent routing validates customers before appointment operations.
- Appointment continuity survives follow-up turns and clears on exit.
- Declining customer creation clears pending validation state.
- Final appointment responses are not duplicated by the writer.
- Successful booking and rescheduling clear their terminal state.
- Existing pending-question expectations account for cleared retrieved-service context.

Why:

The important behavior spans multiple graph boundaries, so node-only tests were insufficient. The compiled integration test verifies that an actual model-produced tool call reaches `ToolNode`, updates state, and returns to the agent for a final answer without requiring a live API or model provider.

## API contract used by the feature

The code expects `DESKIA_API_URL` and the following backend behavior:

| Operation | Request | Required response behavior |
|---|---|---|
| Check availability | `GET /appointments/availability` with `starts_at` and `business_id` | JSON value indicating whether the exact slot is available |
| Book appointment | `POST /appointments/book` with `business_id`, `customer_id`, `starts_at`, and `ends_at` | Successful status and the created appointment as JSON |
| Find customer appointment | `GET /appointments/find_customer_appointment` with `customer_id`, `business_id`, and optional `appointment_date` | One appointment object or an empty value |
| Reschedule appointment | `PATCH /appointments/{appointment_id}/reschedule` with `business_id`, `starts_at`, and `ends_at` | Successful status and the updated appointment as JSON |

The backend must atomically re-check slot availability during booking and rescheduling. `confirmed_slot` is a conversational guard against incorrect tool order; it cannot prevent another client from taking the same slot between requests.

The reschedule endpoint, HTTP verb, and payload still need confirmation against the production API contract, as noted in the tool source.

## Documentation update

File:

- [`docs/2026-08-23-booking-workflow-fixes.md`](2026-08-23-booking-workflow-fixes.md)

Changes:

- Updated the current-capability section to include appointment availability, booking, lookup, and rescheduling.
- Left cancellation and service inquiry under remaining limitations.
- Removed a hard-coded test count that would become stale as the suite grows.

Why:

The project notes should describe the behavior that now exists, while clearly distinguishing implemented tools from deferred work.

## Review findings addressed

The feature review identified four issues, all addressed in the final hardening commit:

1. Exit intents did not clear pending customer-validation state.
2. A successful customer API response with non-object JSON could crash on `.get`.
3. The tests did not yet invoke a compiled tool loop end to end.
4. Documentation contained a brittle hard-coded test count.

The scoped re-review found no remaining critical or important issues in this feature range.

## Verification

Final verification results:

- `uv run python -m unittest discover -s tests -v`: **51 tests passed**.
- `git diff --check`: no whitespace errors.
- Stale `active_flow` and `service_request` references: none in the updated categorizer or parent graph.
- Feature review: all reported findings addressed; ready for integration.

## Checkpoints

| Commit | Purpose |
|---|---|
| `82cf5fb` | Baseline checkpoint before appointment-services work |
| `0023af6` | Expose validated customer identity to the appointment flow |
| `b864f5a` | Add the appointment agent and `ToolNode` loop |
| `3e76342` | Route validated customers into appointment services |
| `b3d7002` | Complete flows without duplicate assistant responses |
| `c4cc6b1` | Update booking workflow documentation |
| `2dfc75b` | Harden exits, API payload validation, and integration coverage |

## Deliberately deferred

- **Appointment cancellation:** no callable cancellation tool or confirmed backend contract is currently available.
- **RAG redesign:** only import-time coupling was removed; retrieval quality and production RAG architecture were not changed.
- **New abstractions or dependencies:** unnecessary for this workflow because the existing state, agent node, tools, and LangGraph primitives cover it.
- **Push or merge:** the implementation remains local until the integration approach is selected.
