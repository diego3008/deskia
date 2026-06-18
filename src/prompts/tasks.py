CATEGORIZER_TASK = """Your task is to analyze incoming messages and classify them into exactly one of the following categories:

- **inquiry**: The message is asking about a product or service (features, pricing, availability, etc.)
- **customer_complaint**: The message expresses dissatisfaction, reports a problem, or requests a fix.
- **customer_feedback**: The message shares an opinion, suggestion, or experience about a product or service.
- **unrelated**: The message does not relate to any product or service.

## Rules
- Return only one category per message.
- If the message could fit multiple categories, choose the most dominant intent.
- Ignore the tone or language of the message — focus only on intent.

## Message to categorize
{message}
"""