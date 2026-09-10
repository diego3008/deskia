# Telegram Appointment Availability and Booking Workflow

Date: 2026-09-09

## Scope

This document covers only:

- collecting the service, date, and time;
- checking appointment availability;
- carrying the selected slot through conversation state;
- confirming or explicitly requesting a booking;
- creating the appointment.

Rescheduling, cancellation, and appointment viewing are intentionally excluded.

## Problems corrected

### Repeated availability checks

The agent could announce that a slot was available and then check the same slot
again instead of booking it. Three state-contract problems contributed to this:

1. Booking validation requires the authoritative appointment end time returned
   by the API. An availability response without `ends_at` was therefore not a
   usable booking slot.
2. The API returned `business_staff_id`, while parts of the agent expected
   `staff_id`. The selected staff member was effectively lost between the
   availability and booking nodes.
3. A customer who first asked only about availability and then explicitly asked
   to book the available slot changed intent from `check_availability` to
   `book_appointment`. That intent change cleared the validated slot and caused
   another availability check followed by an unnecessary yes/no question.

The workflow now uses one canonical staff field, validates complete slot data,
and recognizes an explicit booking request for a just-validated slot as booking
authorization.

### Stale selected staff

An unavailable response cleared `service_id` and `ends_at` but could retain a
staff member selected by an earlier successful check. The unavailable branch now
also clears `business_staff_id`.

## State contract

`MessageGraphState` carries the following appointment fields across Telegram
messages:

| Field | Purpose |
|---|---|
| `appointment_intent` | Active operation: `book_appointment` or `check_availability`. |
| `current_flow` | Keeps follow-up messages inside `appointment_services`. |
| `service_name` | Customer-facing service name used for availability lookup. |
| `starts_at` | Requested timezone-aware appointment start. |
| `ends_at` | Authoritative service end returned by the availability API. |
| `service_id` | Authoritative service identifier returned by the API. |
| `business_staff_id` | Authoritative assigned staff identifier returned by the API. |
| `pending_question` | The question the next customer message is expected to answer. |
| `next_action` | The guarded workflow transition that may run next. |

`clear_appointment_state()` clears all of these appointment-specific values
when a flow succeeds, is abandoned, or fails before availability can be
confirmed. Customer and business identity remain outside this appointment reset.

## Guardrail variables

`pending_question` and `next_action` are persisted workflow state, not text
instructions for the language model.

| Situation | `pending_question` | `next_action` | Meaning |
|---|---|---|---|
| Service or start time is missing | `appointment_details` | `collect_appointment_details` | Preserve the active intent and collect only missing details. |
| Booking intent and slot is available | `booking_confirmation` | `confirm_booking` | Wait for the customer's affirmative confirmation. |
| Availability-only intent and slot is available | `None` | `check_availability` | Report availability without booking; retain the validated slot. |
| Customer explicitly asks to book that available slot | `None` | `book_appointment` after validation | Promote the intent and book directly without another yes/no question. |
| Successful booking | `None` | `None` | The appointment flow is complete. |

A booking can run only when all of these values are present:

- `business_id`;
- `customer_id`;
- `service_id`;
- `business_staff_id`;
- `starts_at`;
- `ends_at`.

The conversational booking guard additionally requires:

- `message_category == "confirmation"`;
- `appointment_intent == "book_appointment"`.

An explicit booking request for a complete availability-only slot is normalized
to that confirmation state before validation. A plain affirmative without an
explicit booking request or pending booking question does not authorize a write.

## Detail collection

`appointment_details_node` extracts only details supplied by the customer:

- service name;
- date and time as `starts_at`.

It preserves previously collected values when a follow-up supplies only the
missing detail. It never invents `ends_at`; the availability API calculates the
end from the selected service and staff assignment.

When both service and start are present:

```text
pending_question = None
next_action = check_availability
```

Otherwise it asks for the missing service, date, or time and keeps:

```text
pending_question = appointment_details
next_action = collect_appointment_details
```

## Availability request

`check_availability_node` calls:

```text
GET {DESKIA_API_URL}/appointments/validate-date
```

with:

```json
{
  "business_id": "...",
  "requested_start_date": "2030-09-21T09:00:00-06:00",
  "service_name": "Limpieza dental"
}
```

`requested_start_date` comes from state `starts_at` and must include a timezone
offset.

The API considers:

- active business status;
- service lookup within the business;
- business timezone and daylight-saving validity;
- future date;
- weekly business hours or a date-specific exception;
- active staff assigned to the service;
- staff working hours;
- service duration and before/after buffers;
- active appointment conflicts;
- staff blocks.

An available response must contain:

```json
{
  "available": true,
  "service_id": "...",
  "business_staff_id": "...",
  "starts_at": "2030-09-21T09:00:00-06:00",
  "ends_at": "2030-09-21T10:00:00-06:00"
}
```

The agent treats `service_id`, `business_staff_id`, and `ends_at` as
authoritative. A truthy or malformed response missing any of those fields is not
presented as bookable.

The endpoint may return plain `false` when no staff member can perform the
service at that time.

## Booking behavior

### Booking requested before availability

```text
Customer: Quiero agendar una limpieza dental el 21 de septiembre a las 9.
Agent: El horario solicitado está disponible. ¿Deseas que lo reserve?
Customer: Sí.
Agent: Listo, tu cita quedó agendada.
```

Because the original intent is already `book_appointment`, successful
availability establishes:

```text
pending_question = booking_confirmation
next_action = confirm_booking
```

The next affirmative reply uses the existing slot and routes to booking without
another availability call.

### Availability first, then explicit booking

```text
Customer: ¿Hay disponibilidad para limpieza dental el 21 de septiembre a las 9?
Agent: El horario solicitado está disponible.
Customer: Okay, ¿podrías agendarme ese día y esa hora?
Agent: Listo, tu cita quedó agendada.
```

The explicit booking request is classified as `new_appointment`. When the
current state is an availability-only flow with a complete validated slot and
`next_action == "check_availability"`, the categorizer:

1. normalizes the message category to `confirmation`;
2. promotes `appointment_intent` to `book_appointment`;
3. preserves the service, staff, start, and end;
4. lets appointment validation select `book_appointment` directly.

There is no second availability call and no additional “¿Deseas que lo reserve?”
prompt.

### Availability-only request

An availability question alone never creates an appointment. The agent reports
the result and retains the complete slot so a later explicit booking request can
reuse it safely.

## Booking request

`book_appointment_node` calls:

```text
POST {DESKIA_API_URL}/appointments/book
```

with:

```json
{
  "business_id": "...",
  "customer_id": "...",
  "service_id": "...",
  "business_staff_id": "...",
  "starts_at": "2030-09-21T09:00:00-06:00",
  "ends_at": "2030-09-21T10:00:00-06:00"
}
```

The API request model and database model use the same
`business_staff_id` name. The API persists both the selected staff and service.

The agent accepts a booking response as successful only when it is a JSON object
containing non-empty `starts_at` and `ends_at`. After success it clears the
appointment state and sends a customer-facing confirmation.

## Failure behavior

| Failure | Result |
|---|---|
| Missing service, date, or time before availability | Ask for the missing details. |
| Naive or invalid start time | Do not call the API; request a valid timezone-aware time. |
| Availability API error | Do not claim availability; clear unusable appointment state. |
| Slot unavailable | Clear `service_id`, `business_staff_id`, and `ends_at`; report unavailable. |
| Malformed available response | Do not present the slot as bookable. |
| Missing booking field | Do not call the booking API; retain collected state. |
| Booking HTTP, validation, or JSON error | Do not claim success; retain collected state for retry. |
| Valid booking response | Clear appointment workflow state and confirm the booking. |

## Telegram continuity requirement

Every Telegram message in the conversation must use the same LangGraph thread
identifier. The second turn relies on the first turn's persisted
`appointment_intent`, `pending_question`, `next_action`, and slot fields.
Starting a new thread for each message discards those guardrails and breaks the
workflow.

## Implementation map

### Agent service

- `src/state.py`: appointment state schema.
- `src/helpers/workflow.py`: terminal/reset state.
- `src/nodes/appointment_services/appointment_details_node.py`: detail extraction.
- `src/nodes/appointment_services/appointment_action_nodes.py`: availability and booking API calls.
- `src/nodes/appointment_services/appointment_validation_node.py`: guarded action selection.
- `src/nodes/message_categorizer_node.py`: follow-up continuity and explicit-booking promotion.
- `src/graph/appointment_services_subgraph.py`: action routing.

### API service

- `src/api/appointments.py`: `validate-date` and `book` endpoints.
- `src/models/appointment.py`: booking request and persisted appointment fields.

## Verification coverage

The automated checks cover:

- missing and partially supplied appointment details;
- timezone-aware availability requests;
- unavailable, HTTP-error, and malformed availability responses;
- required `service_id`, `business_staff_id`, and `ends_at`;
- stale selected-staff cleanup;
- `pending_question` and `next_action` transitions;
- affirmative booking confirmation;
- classifier misclassification of affirmative booking replies;
- explicit booking after availability without a second confirmation;
- exactly one availability call in the normal booking-confirmation flow;
- exact booking payload and terminal state cleanup;
- API mapping of selected service and staff.

Verification performed while implementing these changes:

```text
Agent: 123 passed, 110 subtests passed
API availability/booking focus: 63 passed
```

No live Telegram smoke test was run from the agent repository because Telegram
delivery is handled by the separate API adapter.

## Remaining backend limitations

These are documented requirements, not completed by the changes above:

1. `POST /appointments/book` must atomically re-check availability before
   inserting the appointment. The conversational guard cannot prevent another
   client from taking the slot between availability and booking.
2. The booking status is currently assigned with the numeric value `2`; the API
   assumes that value represents the intended initial status.
3. The booking response currently returns only `starts_at` and `ends_at`.
   Returning appointment and operation identifiers is still required for a
   durable downstream confirmation workflow.
