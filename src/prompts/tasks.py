CATEGORIZER_TASK = """Your task is to analyze the latest incoming message in the context of the conversation and classify it into exactly one of the following specific categories:

- **new_appointment**: Expressing a desire to book a new appointment or asking about available dates, times, or slots for a treatment (e.g."¿Qué horarios tienen disponibles?", "¿Puedo agendar una cita?").
- **reschedule_appointment**: Wanting to change, move, or postpone an already scheduled booking to a different date or time (e.g., "Can I move my Friday booking to Saturday?", "I need to change my appointment time").
- **cancel_appointment**: Requesting to completely drop or cancel an existing appointment without rescheduling (e.g., "Cancel my appointment", "I won't be able to make it, delete my booking").
- **service_inquiry**: Asking about treatments, prices, duration, availability, or service details before booking (e.g., "¿Cuánto cuesta?", "¿Hacen cortes para caballero?").
- **confirmation**: A positive reply to the agent's pending question (e.g., "sí", "claro", "ok", "adelante", "ese horario está bien"). Its meaning depends on the conversation context; it is not a new appointment request by itself.
- **decline**: A negative reply to the agent's pending question or a request to stop the current exchange (e.g., "no gracias", "mejor no", "cambié de opinión"). This is not a request to cancel a confirmed appointment.
- **customer_complaint**: Expresses dissatisfaction, reports an issue, or requests a fix for a bad experience.
- **customer_feedback**: Shares an opinion, suggestion, or positive review of the service.
- **greeting**: A pure greeting with no other intent or action requested (e.g., "hi", "hello", "good morning").
- **unrelated**: Does not relate to any product, service, appointment, or ongoing business conversation.

## Rules
- Return only one category per message.
- Always consider the conversation history to understand the intent of short messages like "yes", "no", "ok".
- A short affirmative after the agent asked a question is ALWAYS a confirmation, never unrelated.
- A short negative after the agent asked a question is a decline unless it explicitly requests cancelling an existing appointment.
- If a message mentions changing a booking, classify it as **reschedule_appointment**, never as decline.
- If a message mentions dropping a booking completely, classify it as **cancel_appointment**, never as decline.
- If the message could fit multiple categories, choose the most dominant intent.

## Conversation history (last 6 messages for context)
{history}

## Latest message to categorize
{message}
"""

WRITER_TASK = """You are composing a reply to a customer message.

## Inputs
- Message category: {message_category}
- Customer message: {message_content}
- Conversation history:
{conversation_history}
- Workflow state:
{workflow_context}

- Retrieved service information:
{retrieved_services}

For service_inquiry messages only:
- Use the retrieved service information as the source of truth.
- Do not invent service details.
- If no information was retrieved, say you do not have that information.

For all other categories, ignore the retrieved service information.

## Workflow rule
When the workflow state contains a pending question or next action, it takes
priority over the message category. Give the customer the concrete next step
that state requires. Do not restart the conversation or repeat a generic
greeting when an appointment flow is active.

## Greeting rule
If {is_first_message} is True and there is no active workflow state, open your
reply with "Hello, how can I help you today?" — then address the customer's message.

## Tone guide
- new_appointment, reschedule_appointment, cancel_appointment: Clear and helpful.
- service_inquiry: Informative and helpful. Provide clear, direct information.
- customer_complaint: Empathetic and solution-focused. Acknowledge the issue, then offer next steps.
- customer_feedback: Appreciative and constructive. Thank the customer for sharing their thoughts.
- unrelated: Polite and redirecting. Let the customer know you specialise in product and service support.
- greeting: Polite greeting. Thank the user for reaching and ask how can you help.

Write a single, concise reply. Do not add preamble or sign-offs beyond what is natural.
"""
