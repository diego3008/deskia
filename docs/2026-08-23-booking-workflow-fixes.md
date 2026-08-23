# Booking Workflow Fixes and Remaining Response Handoff

Date: 2026-08-23

## Objective

Make the appointment workflow preserve multi-turn customer state, route each reply to the correct subgraph, and avoid sending stale or redundant Telegram messages.

## Fixes completed

### 1. Pending-question routing across turns

The parent booking graph and the `user_services` subgraph now recognize these active questions:

- `existing_customer_email`
- `confirm_create_customer`
- `new_customer_details`

Replies to those questions return to `user_services`, even when the message categorizer labels a short answer as `greeting`, `confirmation`, or another category. Customer lookup and creation retry actions also return to the validation flow.

### 2. Customer information collection

The validation node now reads the latest human message and:

- extracts an email address before customer lookup;
- replaces stale customer data when a different email is supplied;
- asks whether a customer should be created after a lookup returns `404`;
- extracts first and last name before customer creation;
- keeps the relevant question pending when the answer is incomplete.

Starting a new appointment, reschedule, or cancellation clears customer-specific data from an abandoned earlier flow.

### 3. Required customer names

`CustomerCreate.first_name` and `CustomerCreate.last_name` are runtime-required fields. `CustomerInput` and the customer-creation tool follow the same contract, and the creation node refuses to call the API until business ID, email, first name, and last name are present.

### 4. API failure handling

Customer lookup and creation now handle HTTP failures and malformed JSON responses. A `404` lookup is treated as a missing customer rather than a generic API failure; retryable failures produce explicit retry actions.

### 5. Appointment categories

`reschedule_appointment` and `cancel_appointment` were added to the structured message-category output so the categorizer and router share the same supported values.

### 6. Message writer in the booking graph

The booking graph now registers `message_writer`. Greetings, customer complaints, and customer feedback route to it, and the node has a terminal edge to `END`.

Appointment, reschedule, cancellation, service-inquiry, pending-question, and retry states continue to route through `user_services`.

### 7. Redundant Telegram response fix

The two reported messages were tested against the configured categorizer through the real listener/categorizer path:

- `Hola, quiero agendar una cita` → `new_appointment`
- `quiero agendar una cita para el 24 de Agosto a las 10 am` → `new_appointment`

This ruled out current misclassification as the source of the repeated greeting.

The actual state hazard was a persisted `message_response`: `user_services` updated workflow fields but did not replace the previous writer response, allowing a Telegram adapter that reads `message_response` to resend the old greeting.

The listener now clears `message_response` at the beginning of every inbound turn. The writer also returns only the new `AIMessage` delta and does not mutate or replace the existing `messages` history; LangGraph's `add_messages` reducer owns that merge.

## Verification

The focused suite currently contains 29 passing tests covering routing, pending questions, customer lookup and creation, required names, graph writer registration, stale-response clearing, and writer message deltas.

`git diff --check` also completes without errors.

## Remaining issue

After `user_services` finishes, the parent graph currently goes directly to `END`. The subgraph can set state such as:

- `pending_question = existing_customer_email`
- `next_action = request_existing_customer_email`
- `pending_question = confirm_create_customer`
- `next_action = request_new_customer_details`

However, it does not convert that state into a customer-facing assistant message. Clearing stale output prevents duplicate greetings, but Telegram can now receive an empty response for these booking states.

The current writer also cannot perform this job yet: it receives the inbound message, category, and first-turn flag, but not `pending_question`, `next_action`, `customer_status`, or recent conversation history.

## Proposed remaining fix

Keep the existing nodes and make the smallest response handoff:

1. Replace the `user_services → END` edge with `user_services → message_writer`.
2. Pass recent conversation history and the relevant workflow fields to the writer prompt.
3. Instruct the writer to answer the current workflow state—for example, request the email when `pending_question` is `existing_customer_email`—instead of restarting with a generic greeting.
4. Preserve the existing direct writer route for greetings, complaints, and feedback.
5. Add focused regression tests proving that the graph reaches the writer after `user_services`, that workflow context is passed to it, and that only one new assistant-message delta is emitted.

This does not add another response node or a template layer. The existing writer remains the single component responsible for customer-facing language.

## Approval gate

The remaining response-handoff change described above has not been implemented. Implementation and its focused test runs require explicit authorization.
