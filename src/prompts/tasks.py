CATEGORIZER_TASK = """Your task is to analyze the latest incoming message in context of the conversation and classify it into exactly one of the following categories:

- **service_request**: Anything about appointments or services — asking about availability or pricing, or wanting to book, reschedule/change, or cancel an existing appointment. "Cancel my appointment" or "move my Friday booking" belong here, NOT in decline.
- **confirmation**: Confirming, agreeing, or responding positively to a previous question (e.g. "yes", "sure", "ok", "go ahead", "sounds good").
- **decline**: Conversationally declining or stopping the current exchange (e.g. "no", "never mind", "don't book it"). This is a reply to the agent, NOT a request to cancel a booked appointment — that is service_request.
- **customer_complaint**: Expresses dissatisfaction, reports a problem, or requests a fix.
- **customer_feedback**: Shares an opinion, suggestion, or experience.
- **greeting**: A greeting with no other intent (e.g. "hi", "hello").
- **unrelated**: Does not relate to any product, service, or ongoing conversation.

## Rules
- Return only one category per message.
- Always consider the conversation history to understand the intent of short messages like "yes", "no", "ok".
- A short affirmative after the agent asked a question is ALWAYS a confirmation, never unrelated.
- "Cancel my appointment" / "reschedule my booking" is ALWAYS service_request, never decline.
- If the message could fit multiple categories, choose the most dominant intent.

## Conversation history (last 6 messages for context)
{history}

## Latest message to categorize
{message}
"""

WRITER_TASK = """You are composing a reply to a customer message.

## Inputs
- Customer message: {message_content}

## Greeting rule
If {is_first_message} is True, open your reply with "Hello, how can I help you today?" — then address the customer's message.

## Tone guide
- service_request: Informative and helpful. Provide clear, direct information.
- customer_complaint: Empathetic and solution-focused. Acknowledge the issue, then offer next steps.
- customer_feedback: Appreciative and constructive. Thank the customer for sharing their thoughts.
- unrelated: Polite and redirecting. Let the customer know you specialise in product and service support.
- greeting: Polite greeting. Thank the user for reaching and ask how can you help.

Write a single, concise reply. Do not add preamble or sign-offs beyond what is natural.
"""