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

Appointment, reschedule, cancellation, service-inquiry, pending-question, and retry states route through `user_services` and then into the writer for one customer-facing reply.

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

### 8. `user_services` response handoff

`user_services` now feeds the existing `message_writer` before the graph ends. The writer receives recent conversation history plus the relevant workflow state:

- `pending_question = existing_customer_email`
- `next_action = request_existing_customer_email`
- `pending_question = confirm_create_customer`
- `next_action = request_new_customer_details`

When a workflow question or action exists, it takes priority over the first-message greeting rule. This prevents a booking request from restarting with a generic greeting and turns the pending state into the next customer-facing question.

An end-to-end graph check for `Hola, quiero agendar una cita para el 24 de Agosto a las 10 am` produced:

> ¡Hola! Con gusto te ayudo a agendar tu cita para el 24 de agosto a las 10:00 am. Para continuar con el proceso, ¿podrías proporcionarme tu correo electrónico?

## Current limitations

The workflow can now guide customer identification conversationally, but it does not yet check availability, create appointments, reschedule appointments, cancel appointments, or answer service inquiries from a service catalog.
